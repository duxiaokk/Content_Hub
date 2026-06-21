from __future__ import annotations

import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import httpx

from apps.workflow_engine.pipeline.linear_pipeline import LinearPipelineRunner, LinearPipelineSpec
from apps.workflow_engine.registry.contracts import ContentAsset, FetchRequest, ProcessContext, PublishTarget
from apps.workflow_engine.registry.plugin_registry import PluginRegistry
from apps.workflow_engine.runtime.observability import WorkflowRunTrace


@dataclass(slots=True)
class WorkflowNodeSpec:
    node_id: str
    stage: str
    component_name: str
    depends_on: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowGraphSpec:
    run_id: str
    workflow_name: str
    source_name: str
    nodes: list[WorkflowNodeSpec]
    lookback_hours: int = 24
    limit: int = 20


class DagWorkflowRunner:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry
        self._linear_runner = LinearPipelineRunner(registry)

    async def run(self, spec: WorkflowGraphSpec) -> dict[str, Any]:
        trace = WorkflowRunTrace(run_id=spec.run_id, workflow_name=spec.workflow_name)
        trace.mark_running()
        workflow_observations = self._empty_workflow_observations()
        reasoning_decisions: list[dict[str, Any]] = []

        # 兼容老的固定三段式 graph，同时支持插入 tool 节点做上下文增强。
        if not any(node.stage == "tool" for node in spec.nodes):
            linear_spec = LinearPipelineSpec(
                fetcher_name=self._get_stage_component(spec, "fetch"),
                processor_name=self._get_stage_component(spec, "process"),
                publisher_name=self._get_stage_component(spec, "publish"),
                fetch_request=FetchRequest(
                    source_name=spec.source_name,
                    lookback_hours=spec.lookback_hours,
                    limit=spec.limit,
                    options=self._stage_options(spec, "fetch"),
                ),
                process_context=ProcessContext(
                    run_id=spec.run_id,
                    options=self._stage_options(spec, "process"),
                ),
                publish_target=PublishTarget(
                    target_name=self._get_stage_component(spec, "publish"),
                    options=self._stage_options(spec, "publish"),
                ),
            )
            results = await self._linear_runner.run(linear_spec)
            workflow_observations["publish_success_rate"] = self._build_publish_success_observation(results)
            for item in results:
                succeeded = item.get("publish_status") == "published"
                trace.record_item(
                    succeeded=succeeded,
                    message=f"content {item.get('content_id')} processed",
                    payload=item,
                )
            final_status = "succeeded" if trace.items_failed == 0 else "partial"
            trace.mark_finished(status=final_status)
            return {
                "run_id": spec.run_id,
                "workflow_name": spec.workflow_name,
                "status": final_status,
                "results": results,
                "observations": workflow_observations,
                "reasoning_decisions": reasoning_decisions,
                "trace": trace.snapshot(),
            }

        results, workflow_observations, reasoning_decisions = await self._run_with_tool_nodes(spec)
        for item in results:
            succeeded = item.get("publish_status") == "published"
            trace.record_item(
                succeeded=succeeded,
                message=f"content {item.get('content_id')} processed",
                payload=item,
            )
        final_status = "succeeded" if trace.items_failed == 0 else "partial"
        trace.mark_finished(status=final_status)
        return {
            "run_id": spec.run_id,
            "workflow_name": spec.workflow_name,
            "status": final_status,
            "results": results,
            "observations": workflow_observations,
            "reasoning_decisions": reasoning_decisions,
            "trace": trace.snapshot(),
        }

    async def _run_with_tool_nodes(
        self,
        spec: WorkflowGraphSpec,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        executed: set[str] = set()
        node_outputs: dict[str, dict[str, Any]] = {}
        fetched_assets: list[ContentAsset] = []
        processed_assets: list[ContentAsset] = []
        results: list[dict[str, Any]] = []
        workflow_observations = self._empty_workflow_observations()
        reasoning_decisions: list[dict[str, Any]] = []

        while len(executed) < len(spec.nodes):
            ready_nodes = [
                node for node in spec.nodes
                if node.node_id not in executed
                and all(dep in executed for dep in node.depends_on)
            ]
            if not ready_nodes:
                raise RuntimeError("workflow graph has circular dependency or unresolved stage dependency")

            for node in ready_nodes:
                if node.stage == "fetch":
                    fetched_assets = await self._execute_fetch_node(spec, node)
                    workflow_observations["fetch_quality"] = self._build_fetch_quality_observation(
                        fetched_assets=fetched_assets,
                        fetch_limit=spec.limit,
                    )
                    node_outputs[node.node_id] = {"kind": "fetch", "assets": fetched_assets}
                elif node.stage == "tool":
                    tool_result = await self._execute_tool_node(spec, node, node_outputs, fetched_assets, processed_assets, results)
                    self._update_tool_hit_rate_observation(workflow_observations, tool_result)
                    node_outputs[node.node_id] = {
                        "kind": "tool",
                        "result_key": str(node.options.get("result_key") or node.node_id),
                        "result": tool_result,
                    }
                elif node.stage == "process":
                    self._append_process_reasoning_decision(reasoning_decisions, workflow_observations, node)
                    input_assets = self._resolve_input_assets(node, node_outputs, fallback=fetched_assets)
                    processed_assets = await self._execute_process_node(
                        spec,
                        node,
                        input_assets,
                        node_outputs,
                        workflow_observations,
                        reasoning_decisions,
                    )
                    workflow_observations["process_quality"] = self._build_process_quality_observation(processed_assets)
                    node_outputs[node.node_id] = {"kind": "process", "assets": processed_assets}
                elif node.stage == "publish":
                    self._append_publish_reasoning_decision(reasoning_decisions, workflow_observations, node)
                    input_assets = self._resolve_input_assets(node, node_outputs, fallback=processed_assets)
                    results = await self._execute_publish_node(
                        spec,
                        node,
                        input_assets,
                        node_outputs,
                        workflow_observations,
                        reasoning_decisions,
                    )
                    workflow_observations["publish_success_rate"] = self._build_publish_success_observation(results)
                    node_outputs[node.node_id] = {"kind": "publish", "results": results}
                else:
                    raise KeyError(f"unsupported workflow stage '{node.stage}'")
                executed.add(node.node_id)

        publish_outputs = [node_outputs[node.node_id] for node in spec.nodes if node.stage == "publish"]
        if publish_outputs:
            return list(publish_outputs[-1].get("results", [])), workflow_observations, reasoning_decisions
        return results, workflow_observations, reasoning_decisions

    async def _execute_fetch_node(self, spec: WorkflowGraphSpec, node: WorkflowNodeSpec) -> list[ContentAsset]:
        fetcher = self.registry.get_fetcher(node.component_name)
        fetched_items = await fetcher.fetch(
            FetchRequest(
                source_name=spec.source_name,
                lookback_hours=spec.lookback_hours,
                limit=spec.limit,
                options=dict(node.options),
            )
        )
        assets: list[ContentAsset] = []
        for item in fetched_items:
            content_id = self._linear_runner.repository.upsert_fetched_item(item)
            assets.append(
                ContentAsset(
                    content_id=content_id,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    title=item.title,
                    raw_content=item.raw_content,
                    processed_content=None,
                    source_url=item.source_url,
                    metadata=dict(item.metadata),
                )
            )
        return assets

    async def _execute_process_node(
        self,
        spec: WorkflowGraphSpec,
        node: WorkflowNodeSpec,
        assets: list[ContentAsset],
        node_outputs: dict[str, dict[str, Any]],
        workflow_observations: dict[str, Any],
        reasoning_decisions: list[dict[str, Any]],
    ) -> list[ContentAsset]:
        processor = self.registry.get_processor(node.component_name)
        context = ProcessContext(
            run_id=spec.run_id,
            options=self._merge_node_options(
                node,
                node_outputs,
                workflow_observations=workflow_observations,
                reasoning_decisions=reasoning_decisions,
            ),
        )
        processed_assets: list[ContentAsset] = []
        for asset in assets:
            process_result = await processor.process(asset, context)
            self._linear_runner.repository.mark_processed(
                process_result.content,
                status=process_result.status,
                error_message=process_result.warnings[0] if process_result.warnings else None,
            )
            processed_assets.append(process_result.content)
        return processed_assets

    async def _execute_publish_node(
        self,
        spec: WorkflowGraphSpec,
        node: WorkflowNodeSpec,
        assets: list[ContentAsset],
        node_outputs: dict[str, dict[str, Any]],
        workflow_observations: dict[str, Any],
        reasoning_decisions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        publisher = self.registry.get_publisher(node.component_name)
        publish_target = PublishTarget(
            target_name=node.component_name,
            options=self._merge_node_options(
                node,
                node_outputs,
                workflow_observations=workflow_observations,
                reasoning_decisions=reasoning_decisions,
            ),
        )
        results: list[dict[str, Any]] = []
        for asset in assets:
            publish_result = await publisher.publish(asset, publish_target)
            self._linear_runner.repository.mark_published(
                asset,
                target_name=publish_target.target_name,
                result=publish_result,
            )
            results.append(
                {
                    "content_id": asset.content_id,
                    "source_id": asset.source_id,
                    "process_status": "processed",
                    "publish_status": publish_result.status,
                    "target_name": publish_result.target_name,
                    "run_id": spec.run_id,
                }
            )
        return results

    async def _execute_tool_node(
        self,
        spec: WorkflowGraphSpec,
        node: WorkflowNodeSpec,
        node_outputs: dict[str, dict[str, Any]],
        fetched_assets: list[ContentAsset],
        processed_assets: list[ContentAsset],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        options = dict(node.options)
        payload = dict(options.get("payload") or {})
        tool_context = self._build_tool_context(
            spec=spec,
            node=node,
            payload=payload,
            node_outputs=node_outputs,
            fetched_assets=fetched_assets,
            processed_assets=processed_assets,
            results=results,
        )
        payload["context"] = tool_context
        if "intent" in options and "intent" not in payload:
            payload["intent"] = str(options.get("intent") or "")
        elif "intent_template" in options and "intent" not in payload:
            payload["intent"] = self._render_intent_template(str(options.get("intent_template") or ""), tool_context)

        tool_plan = dict(options.get("tool_plan") or {})
        if tool_plan.get("steps"):
            return await self._execute_tool_plan(
                spec=spec,
                node=node,
                options=options,
                payload=payload,
                tool_context=tool_context,
            )

        if "tool_calls" in options and "tool_calls" not in payload:
            payload["tool_calls"] = list(options.get("tool_calls") or [])

        data = await self._invoke_tool_agent(
            run_id=spec.run_id,
            task_type=str(options.get("task_type") or "tool.execute"),
            payload=payload,
            options=options,
        )
        return data.get("result", {})

    async def _execute_tool_plan(
        self,
        *,
        spec: WorkflowGraphSpec,
        node: WorkflowNodeSpec,
        options: dict[str, Any],
        payload: dict[str, Any],
        tool_context: dict[str, Any],
    ) -> dict[str, Any]:
        tool_plan = dict(options.get("tool_plan") or {})
        steps = list(tool_plan.get("steps") or [])
        tool_state = self._build_tool_state(
            tool_context=tool_context,
            payload=payload,
            outputs={},
            last_output=None,
        )
        step_results: list[dict[str, Any]] = []
        outputs: dict[str, Any] = {}

        for index, raw_step in enumerate(steps, start=1):
            step = dict(raw_step or {})
            step_id = str(step.get("id") or f"step_{index}")
            output_key = str(step.get("output_key") or step_id)
            on_error = str(step.get("on_error") or "abort").lower()
            max_retries = max(int(step.get("max_retries") or 0), 0)

            attempt = 0
            while True:
                try:
                    result = await self._execute_tool_plan_step(
                        run_id=spec.run_id,
                        node=node,
                        step=step,
                        options=options,
                        tool_state=tool_state,
                    )
                    outputs[output_key] = result
                    tool_state = self._build_tool_state(
                        tool_context=tool_context,
                        payload=payload,
                        outputs=outputs,
                        last_output=result,
                    )
                    step_results.append(
                        {
                            "id": step_id,
                            "tool_name": str(step.get("tool_name") or ""),
                            "status": "succeeded",
                            "attempts": attempt + 1,
                            "output_key": output_key,
                        }
                    )
                    break
                except Exception as exc:
                    if attempt < max_retries:
                        attempt += 1
                        continue

                    if on_error == "continue":
                        error_result = {"error": str(exc), "step_id": step_id, "status": "failed"}
                        outputs[output_key] = error_result
                        tool_state = self._build_tool_state(
                            tool_context=tool_context,
                            payload=payload,
                            outputs=outputs,
                            last_output=error_result,
                        )
                        step_results.append(
                            {
                                "id": step_id,
                                "tool_name": str(step.get("tool_name") or ""),
                                "status": "continued",
                                "attempts": attempt + 1,
                                "output_key": output_key,
                                "error": str(exc),
                            }
                        )
                        break
                    if on_error == "fallback":
                        fallback_output = deepcopy(
                            step.get("fallback_output", step.get("fallback_value", {}))
                        )
                        outputs[output_key] = fallback_output
                        tool_state = self._build_tool_state(
                            tool_context=tool_context,
                            payload=payload,
                            outputs=outputs,
                            last_output=fallback_output,
                        )
                        step_results.append(
                            {
                                "id": step_id,
                                "tool_name": str(step.get("tool_name") or ""),
                                "status": "fallback",
                                "attempts": attempt + 1,
                                "output_key": output_key,
                                "error": str(exc),
                            }
                        )
                        break
                    raise RuntimeError(f"tool plan step '{step_id}' failed: {exc}") from exc

        return {
            "tool_state": tool_state,
            "step_results": step_results,
            "outputs": outputs,
            "last_output": tool_state.get("last_output"),
        }

    async def _execute_tool_plan_step(
        self,
        *,
        run_id: str,
        node: WorkflowNodeSpec,
        step: dict[str, Any],
        options: dict[str, Any],
        tool_state: dict[str, Any],
    ) -> Any:
        tool_name = str(step.get("tool_name") or "").strip()
        if not tool_name:
            raise ValueError("tool plan step must define tool_name")

        raw_input = step.get("input_template", step.get("parameters", {}))
        rendered_input = self._render_tool_template(raw_input, tool_state)
        step_payload = dict(step.get("payload") or {})
        if "context" not in step_payload:
            step_payload["context"] = dict(tool_state.get("context") or {})
        step_payload["tool_state"] = tool_state
        step_payload["tool_calls"] = [{"tool_name": tool_name, "parameters": rendered_input}]
        if step.get("intent") and "intent" not in step_payload:
            step_payload["intent"] = str(step.get("intent") or "")
        elif step.get("intent_template") and "intent" not in step_payload:
            step_payload["intent"] = self._render_tool_template(str(step.get("intent_template") or ""), tool_state)

        data = await self._invoke_tool_agent(
            run_id=run_id,
            task_type=str(step.get("task_type") or options.get("task_type") or "tool.execute"),
            payload=step_payload,
            options={**options, **dict(step.get("request_options") or {})},
        )
        return data.get("result", {})

    async def _invoke_tool_agent(
        self,
        *,
        run_id: str,
        task_type: str,
        payload: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = str(
            options.get("agent_url")
            or os.getenv("TOOL_CALLING_AGENT_BASE_URL")
            or "http://127.0.0.1:8120"
        ).rstrip("/")
        internal_token = str(
            options.get("internal_token")
            or os.getenv("SCHEDULER_INTERNAL_TOKEN")
            or os.getenv("INTERNAL_TOKEN")
            or "local-dev-scheduler-token"
        )
        async with httpx.AsyncClient(timeout=float(options.get("timeout_seconds", 30.0))) as client:
            response = await client.post(
                f"{base_url}/api/internal/agent/run",
                json={"task_type": task_type, "trace_id": run_id, "payload": payload},
                headers={"x-internal-token": internal_token},
            )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _resolve_input_assets(
        node: WorkflowNodeSpec,
        node_outputs: dict[str, dict[str, Any]],
        *,
        fallback: list[ContentAsset],
    ) -> list[ContentAsset]:
        for dep in node.depends_on:
            dep_output = node_outputs.get(dep)
            if not dep_output:
                continue
            if dep_output.get("kind") in {"fetch", "process"}:
                return list(dep_output.get("assets") or [])
        return list(fallback)

    @staticmethod
    def _merge_node_options(
        node: WorkflowNodeSpec,
        node_outputs: dict[str, dict[str, Any]],
        *,
        workflow_observations: dict[str, Any] | None = None,
        reasoning_decisions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        merged = dict(node.options)
        tool_results = dict(merged.get("tool_results") or {})
        for dep in node.depends_on:
            dep_output = node_outputs.get(dep)
            if not dep_output or dep_output.get("kind") != "tool":
                continue
            result_key = str(dep_output.get("result_key") or dep)
            merge_mode = str(node.options.get("merge_mode") or dep_output.get("merge_mode") or "nested")
            result = dep_output.get("result")
            if merge_mode == "flatten" and isinstance(result, dict):
                merged.update(result)
            elif merge_mode == "replace":
                merged[result_key] = result
            else:
                merged.setdefault(result_key, result)
            tool_results[result_key] = result
        if tool_results:
            merged["tool_results"] = tool_results
        if workflow_observations:
            merged["workflow_observations"] = deepcopy(workflow_observations)
        if reasoning_decisions:
            merged["workflow_reasoning_decisions"] = deepcopy(reasoning_decisions)
        return merged

    def _build_tool_context(
        self,
        *,
        spec: WorkflowGraphSpec,
        node: WorkflowNodeSpec,
        payload: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
        fetched_assets: list[ContentAsset],
        processed_assets: list[ContentAsset],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        base_context = dict(payload.get("context") or {})
        candidate_fields = {
            "workflow_name": spec.workflow_name,
            "source_name": spec.source_name,
            "run_id": spec.run_id,
            "fetched_items": self._serialize_assets(fetched_assets),
            "processed_items": self._serialize_assets(processed_assets),
            "publish_results": list(results),
            "workflow_observations": self._empty_workflow_observations(),
            "upstream_outputs": {
                dep: self._serialize_node_output(node_outputs[dep]) for dep in node.depends_on if dep in node_outputs
            },
        }
        include_fields = node.options.get("include_fields")
        if isinstance(include_fields, list) and include_fields:
            for field_name in include_fields:
                field_text = str(field_name).strip()
                if field_text in candidate_fields and field_text not in base_context:
                    base_context[field_text] = candidate_fields[field_text]
        else:
            for field_name, field_value in candidate_fields.items():
                base_context.setdefault(field_name, field_value)
        return base_context

    @staticmethod
    def _build_tool_state(
        *,
        tool_context: dict[str, Any],
        payload: dict[str, Any],
        outputs: dict[str, Any],
        last_output: Any,
    ) -> dict[str, Any]:
        return {
            "context": deepcopy(tool_context),
            "payload": deepcopy(payload),
            "outputs": deepcopy(outputs),
            "last_output": deepcopy(last_output),
        }

    @staticmethod
    def _render_intent_template(template: str, tool_context: dict[str, Any]) -> str:
        text = template or ""
        flattened = {
            "workflow_name": str(tool_context.get("workflow_name") or ""),
            "source_name": str(tool_context.get("source_name") or ""),
            "run_id": str(tool_context.get("run_id") or ""),
            "fetched_count": str(len(tool_context.get("fetched_items") or [])),
            "processed_count": str(len(tool_context.get("processed_items") or [])),
            "publish_count": str(len(tool_context.get("publish_results") or [])),
            "first_title": str(((tool_context.get("fetched_items") or [{}])[0] or {}).get("title") or ""),
        }
        for key, value in flattened.items():
            text = text.replace(f"{{{key}}}", value)
        return re.sub(r"\{[^{}]+\}", "", text).strip()

    @classmethod
    def _render_tool_template(cls, value: Any, tool_state: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._render_tool_template(item, tool_state) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._render_tool_template(item, tool_state) for item in value]
        if not isinstance(value, str):
            return value

        exact_match = re.fullmatch(r"\{\{\s*([^{}]+?)\s*\}\}|\{\s*([^{}]+?)\s*\}", value)
        if exact_match:
            path = exact_match.group(1) or exact_match.group(2) or ""
            return cls._resolve_template_value(path, tool_state)

        def replace(match: re.Match[str]) -> str:
            path = match.group(1) or match.group(2) or ""
            resolved = cls._resolve_template_value(path, tool_state)
            if resolved is None:
                return ""
            return str(resolved)

        return re.sub(r"\{\{\s*([^{}]+?)\s*\}\}|\{\s*([^{}]+?)\s*\}", replace, value)

    @staticmethod
    def _resolve_template_value(path: str, tool_state: dict[str, Any]) -> Any:
        current: Any = tool_state
        for segment in [part for part in path.split(".") if part]:
            if isinstance(current, dict):
                current = current.get(segment)
                continue
            if isinstance(current, list):
                try:
                    current = current[int(segment)]
                except (TypeError, ValueError, IndexError):
                    return None
                continue
            return None
        return deepcopy(current)

    @staticmethod
    def _serialize_assets(assets: list[ContentAsset]) -> list[dict[str, Any]]:
        return [
            {
                "content_id": asset.content_id,
                "source_type": asset.source_type,
                "source_id": asset.source_id,
                "title": asset.title,
                "source_url": asset.source_url,
            }
            for asset in assets
        ]

    @staticmethod
    def _serialize_node_output(output: dict[str, Any]) -> dict[str, Any]:
        kind = str(output.get("kind") or "unknown")
        if kind in {"fetch", "process"}:
            return {"kind": kind, "items": DagWorkflowRunner._serialize_assets(list(output.get("assets") or []))}
        if kind == "tool":
            return {"kind": kind, "result_key": output.get("result_key"), "result": output.get("result")}
        if kind == "publish":
            return {"kind": kind, "results": list(output.get("results") or [])}
        return dict(output)

    @staticmethod
    def _empty_workflow_observations() -> dict[str, Any]:
        return {
            "fetch_quality": {},
            "tool_hit_rate": {"attempts": 0, "hits": 0, "hit_rate": 0.0},
            "process_quality": {},
            "publish_success_rate": {},
            "review_failure_reasons": {"top_reasons": [], "counts": {}},
        }

    @staticmethod
    def _build_fetch_quality_observation(
        *,
        fetched_assets: list[ContentAsset],
        fetch_limit: int,
    ) -> dict[str, Any]:
        total = len(fetched_assets)
        populated = sum(1 for asset in fetched_assets if str(asset.raw_content or "").strip())
        coverage_ratio = round(populated / total, 4) if total else 0.0
        fullness_ratio = round(min(total / max(fetch_limit, 1), 1.0), 4) if fetch_limit else 1.0
        quality_score = round(min(1.0, (coverage_ratio * 0.7) + (fullness_ratio * 0.3)), 4)
        return {
            "fetched_count": total,
            "content_populated_count": populated,
            "coverage_ratio": coverage_ratio,
            "fullness_ratio": fullness_ratio,
            "quality_score": quality_score,
        }

    @staticmethod
    def _update_tool_hit_rate_observation(workflow_observations: dict[str, Any], tool_result: dict[str, Any]) -> None:
        tool_hit_rate = dict(workflow_observations.get("tool_hit_rate") or {})
        attempts = int(tool_hit_rate.get("attempts") or 0) + 1
        hits = int(tool_hit_rate.get("hits") or 0)
        if DagWorkflowRunner._is_tool_result_hit(tool_result):
            hits += 1
        workflow_observations["tool_hit_rate"] = {
            "attempts": attempts,
            "hits": hits,
            "hit_rate": round(hits / max(attempts, 1), 4),
        }

    @staticmethod
    def _is_tool_result_hit(tool_result: dict[str, Any]) -> bool:
        if not isinstance(tool_result, dict):
            return False
        if tool_result.get("success") is True:
            return True
        if isinstance(tool_result.get("results"), list) and tool_result.get("results"):
            return True
        if isinstance(tool_result.get("result"), dict) and tool_result.get("result"):
            return True
        outputs = tool_result.get("outputs")
        if isinstance(outputs, dict) and bool(outputs):
            return True
        return bool(tool_result)

    @staticmethod
    def _build_process_quality_observation(processed_assets: list[ContentAsset]) -> dict[str, Any]:
        scores: list[float] = []
        for asset in processed_assets:
            score = asset.metadata.get("rewrite_critique_score")
            if score is None:
                continue
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                continue
        return {
            "processed_count": len(processed_assets),
            "scored_count": len(scores),
            "average_quality_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        }

    @staticmethod
    def _build_publish_success_observation(results: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(results)
        succeeded = sum(1 for result in results if result.get("publish_status") == "published")
        return {
            "total": total,
            "succeeded": succeeded,
            "success_rate": round(succeeded / max(total, 1), 4) if total else 0.0,
        }

    @staticmethod
    def _append_process_reasoning_decision(
        reasoning_decisions: list[dict[str, Any]],
        workflow_observations: dict[str, Any],
        node: WorkflowNodeSpec,
    ) -> None:
        fetch_quality = dict(workflow_observations.get("fetch_quality") or {})
        tool_hit_rate = dict(workflow_observations.get("tool_hit_rate") or {})
        quality_score = float(fetch_quality.get("quality_score") or 0.0)
        attempts = int(tool_hit_rate.get("attempts") or 0)
        hit_rate = float(tool_hit_rate.get("hit_rate") or 0.0)
        needs_more_context = quality_score < 0.55 or (attempts > 0 and hit_rate < 0.5)
        reasoning_decisions.append(
            {
                "stage": "process",
                "node_id": node.node_id,
                "decision": "supplement_tooling" if needs_more_context else "proceed",
                "reason": "fetch/tool observations indicate context gap" if needs_more_context else "observations acceptable",
            }
        )

    @staticmethod
    def _append_publish_reasoning_decision(
        reasoning_decisions: list[dict[str, Any]],
        workflow_observations: dict[str, Any],
        node: WorkflowNodeSpec,
    ) -> None:
        process_quality = dict(workflow_observations.get("process_quality") or {})
        review_failures = dict(workflow_observations.get("review_failure_reasons") or {})
        average_quality_score = float(process_quality.get("average_quality_score") or 0.0)
        needs_quality_gate = average_quality_score < 0.7 or bool(review_failures.get("top_reasons"))
        reasoning_decisions.append(
            {
                "stage": "publish",
                "node_id": node.node_id,
                "decision": "enter_quality_gate" if needs_quality_gate else "direct_publish",
                "reason": "process quality is low or recent review failures exist"
                if needs_quality_gate
                else "process quality acceptable",
            }
        )

    @staticmethod
    def _get_stage_component(spec: WorkflowGraphSpec, stage: str) -> str:
        for node in spec.nodes:
            if node.stage == stage:
                return node.component_name
        raise KeyError(f"workflow stage '{stage}' is required")

    @staticmethod
    def _stage_options(spec: WorkflowGraphSpec, stage: str) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for node in spec.nodes:
            if node.stage == stage:
                merged.update(node.options)
        return merged
