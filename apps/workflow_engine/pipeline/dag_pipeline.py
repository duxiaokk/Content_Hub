from __future__ import annotations

import os
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
                "trace": trace.snapshot(),
            }

        results = await self._run_with_tool_nodes(spec)
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
            "trace": trace.snapshot(),
        }

    async def _run_with_tool_nodes(self, spec: WorkflowGraphSpec) -> list[dict[str, Any]]:
        executed: set[str] = set()
        node_outputs: dict[str, dict[str, Any]] = {}
        fetched_assets: list[ContentAsset] = []
        processed_assets: list[ContentAsset] = []
        results: list[dict[str, Any]] = []

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
                    node_outputs[node.node_id] = {"kind": "fetch", "assets": fetched_assets}
                elif node.stage == "tool":
                    tool_result = await self._execute_tool_node(spec, node, node_outputs, fetched_assets, processed_assets, results)
                    node_outputs[node.node_id] = {
                        "kind": "tool",
                        "result_key": str(node.options.get("result_key") or node.node_id),
                        "result": tool_result,
                    }
                elif node.stage == "process":
                    input_assets = self._resolve_input_assets(node, node_outputs, fallback=fetched_assets)
                    processed_assets = await self._execute_process_node(spec, node, input_assets, node_outputs)
                    node_outputs[node.node_id] = {"kind": "process", "assets": processed_assets}
                elif node.stage == "publish":
                    input_assets = self._resolve_input_assets(node, node_outputs, fallback=processed_assets)
                    results = await self._execute_publish_node(spec, node, input_assets, node_outputs)
                    node_outputs[node.node_id] = {"kind": "publish", "results": results}
                else:
                    raise KeyError(f"unsupported workflow stage '{node.stage}'")
                executed.add(node.node_id)

        publish_outputs = [node_outputs[node.node_id] for node in spec.nodes if node.stage == "publish"]
        if publish_outputs:
            return list(publish_outputs[-1].get("results", []))
        return results

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
    ) -> list[ContentAsset]:
        processor = self.registry.get_processor(node.component_name)
        context = ProcessContext(
            run_id=spec.run_id,
            options=self._merge_node_options(node, node_outputs),
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
    ) -> list[dict[str, Any]]:
        publisher = self.registry.get_publisher(node.component_name)
        publish_target = PublishTarget(
            target_name=node.component_name,
            options=self._merge_node_options(node, node_outputs),
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
        if "tool_calls" in options and "tool_calls" not in payload:
            payload["tool_calls"] = list(options.get("tool_calls") or [])
        if "intent" in options and "intent" not in payload:
            payload["intent"] = str(options.get("intent") or "")

        tool_context = dict(payload.get("context") or {})
        tool_context.setdefault("workflow_name", spec.workflow_name)
        tool_context.setdefault("source_name", spec.source_name)
        tool_context.setdefault("fetched_items", self._serialize_assets(fetched_assets))
        tool_context.setdefault("processed_items", self._serialize_assets(processed_assets))
        tool_context.setdefault("publish_results", list(results))
        tool_context.setdefault(
            "upstream_outputs",
            {dep: self._serialize_node_output(node_outputs[dep]) for dep in node.depends_on if dep in node_outputs},
        )
        payload["context"] = tool_context

        task_type = str(options.get("task_type") or "tool.execute")
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
                json={"task_type": task_type, "trace_id": spec.run_id, "payload": payload},
                headers={"x-internal-token": internal_token},
            )
        response.raise_for_status()
        data = response.json()
        return data.get("result", {})

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
    def _merge_node_options(node: WorkflowNodeSpec, node_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        merged = dict(node.options)
        tool_results = dict(merged.get("tool_results") or {})
        for dep in node.depends_on:
            dep_output = node_outputs.get(dep)
            if not dep_output or dep_output.get("kind") != "tool":
                continue
            result_key = str(dep_output.get("result_key") or dep)
            tool_results[result_key] = dep_output.get("result")
            merged.setdefault(result_key, dep_output.get("result"))
        if tool_results:
            merged["tool_results"] = tool_results
        return merged

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
