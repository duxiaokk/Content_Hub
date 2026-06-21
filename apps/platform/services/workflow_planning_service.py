from __future__ import annotations

import asyncio
import uuid
from typing import Any

from agents.base_agent import AgentConfig
from agents.planner_agent import PlannerAgent
from apps.platform.services.agent_memory_service import AgentMemoryService
from apps.platform.scheduler_center.orchestration_schemas import ExecutionPlan, PlanTask


class WorkflowPlanningService:
    """将自然语言意图映射为最小可执行 workflow payload。"""

    def plan_workflow(
        self,
        *,
        intent: str,
        context: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> tuple[ExecutionPlan, dict[str, Any]]:
        resolved_context = dict(context or {})
        resolved_constraints = dict(constraints or {})

        fetcher_name = self._resolve_fetcher(intent, resolved_context)
        source_name = str(resolved_context.get("source_name") or fetcher_name)
        processor_name = str(resolved_context.get("processor_name") or self._resolve_processor(intent))
        publisher_name = str(resolved_context.get("publisher_name") or self._resolve_publisher(intent))
        workflow_name = str(resolved_context.get("workflow_name") or "content.workflow.planned")
        lookback_hours = int(resolved_context.get("lookback_hours") or resolved_constraints.get("lookback_hours") or 24)
        limit = int(resolved_context.get("limit") or resolved_constraints.get("limit") or 20)
        lookback_hours, limit, memory_tuning = self._apply_memory_tuning(
            workflow_name=workflow_name,
            lookback_hours=lookback_hours,
            limit=limit,
        )
        observation_tuning = self._apply_observation_tuning(
            workflow_name=workflow_name,
            context=resolved_context,
        )

        fetch_options = dict(resolved_context.get("fetch_options") or {})
        process_options = dict(resolved_context.get("process_options") or {})
        publish_options = dict(resolved_context.get("publish_options") or {})
        if observation_tuning.get("enable_quality_gate"):
            publish_options.setdefault("enable_quality_gate", True)
        if observation_tuning.get("process_options"):
            process_options.update(dict(observation_tuning.get("process_options") or {}))
        rewrite_preferences = AgentMemoryService().build_rewrite_preferences(
            {
                **resolved_context,
                "workflow_name": workflow_name,
            }
        )
        process_options = self._merge_rewrite_preferences(process_options, rewrite_preferences)
        planner_plan = self._decompose_with_planner(
            intent=intent,
            context={
                **resolved_context,
                "workflow_name": workflow_name,
                "source_name": source_name,
                "fetcher_name": fetcher_name,
                "processor_name": processor_name,
                "publisher_name": publisher_name,
                "lookback_hours": lookback_hours,
                "limit": limit,
            },
            constraints=resolved_constraints,
        )
        nodes, plan_tasks = self._build_nodes_and_tasks_from_plan(
            planner_plan=planner_plan,
            source_name=source_name,
            fetcher_name=fetcher_name,
            processor_name=processor_name,
            publisher_name=publisher_name,
            fetch_options=fetch_options,
            process_options=process_options,
            publish_options=publish_options,
            default_tool_options=self._build_tool_options(intent, resolved_context),
            insert_tool_before_process=bool(observation_tuning.get("insert_tool_before_process")),
        )
        next_run_suggestions = self._build_next_run_suggestions(
            workflow_name=workflow_name,
            observation_tuning=observation_tuning,
            memory_tuning=memory_tuning,
        )

        payload = {
            "workflow_name": workflow_name,
            "source_name": source_name,
            "fetcher_name": fetcher_name,
            "processor_name": processor_name,
            "publisher_name": publisher_name,
            "lookback_hours": lookback_hours,
            "limit": limit,
            "fetch_options": fetch_options,
            "process_options": process_options,
            "publish_options": publish_options,
            "nodes": nodes,
            "planning_observations": observation_tuning.get("observations") or {},
            "next_run_suggestions": next_run_suggestions,
        }
        plan = ExecutionPlan(
            plan_id=str(planner_plan.get("plan_id") or uuid.uuid4()),
            intent=intent,
            tasks=plan_tasks,
            estimated_duration_seconds=float(len(plan_tasks) * 5),
            metadata={
                "workflow_name": workflow_name,
                "source_name": source_name,
                "memory_tuning": memory_tuning,
                "observation_tuning": observation_tuning,
                "next_run_suggestions": next_run_suggestions,
                "rewrite_preferences": rewrite_preferences,
                "planner_tasks": list(planner_plan.get("tasks") or []),
            },
        )
        return plan, payload

    def _decompose_with_planner(
        self,
        *,
        intent: str,
        context: dict[str, Any],
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        capabilities = [
            {"agent_key": "workflow-fetch", "name": "Workflow Fetch", "task_types": ["workflow.fetch"]},
            {"agent_key": "tool-calling-agent", "name": "Tool Calling Agent", "task_types": ["tool.execute"]},
            {"agent_key": "workflow-process", "name": "Workflow Process", "task_types": ["workflow.process"]},
            {"agent_key": "workflow-publish", "name": "Workflow Publish", "task_types": ["workflow.publish"]},
        ]
        agent = PlannerAgent(
            AgentConfig(
                agent_key="planner-agent",
                task_types=["plan.decompose"],
                mock_llm=True,
            )
        )
        payload = {
            "intent": intent,
            "context": context,
            "constraints": constraints,
            "available_capabilities": capabilities,
        }
        try:
            return asyncio.run(agent.execute("plan.decompose", payload, None))
        except RuntimeError:
            return agent._plan_with_rules(intent, capabilities, context)  # noqa: SLF001

    def _build_nodes_and_tasks_from_plan(
        self,
        *,
        planner_plan: dict[str, Any],
        source_name: str,
        fetcher_name: str,
        processor_name: str,
        publisher_name: str,
        fetch_options: dict[str, Any],
        process_options: dict[str, Any],
        publish_options: dict[str, Any],
        default_tool_options: dict[str, Any],
        insert_tool_before_process: bool,
    ) -> tuple[list[dict[str, Any]], list[PlanTask]]:
        planner_tasks = list(planner_plan.get("tasks") or [])
        nodes: list[dict[str, Any]] = []
        tasks: list[PlanTask] = []
        has_fetch = False
        has_process = False
        has_publish = False

        for raw_task in planner_tasks:
            task_key = str(raw_task.get("task_key") or f"task-{len(tasks) + 1}")
            task_type = str(raw_task.get("task_type") or "")
            description = str(raw_task.get("description") or "")
            depends_on = [str(dep) for dep in raw_task.get("depends_on", []) if str(dep).strip()]
            input_payload = dict(raw_task.get("input_payload") or {})

            if task_type == "workflow.fetch" and self._looks_like_fetch_task(task_key, description, input_payload):
                has_fetch = True
                nodes.append(
                    {
                        "node_id": task_key,
                        "stage": "fetch",
                        "component_name": str(input_payload.get("fetcher_name") or fetcher_name),
                        "depends_on": depends_on,
                        "options": {**fetch_options, **dict(input_payload.get("fetch_options") or {})},
                    }
                )
                tasks.append(
                    PlanTask(
                        task_key=task_key,
                        task_type=task_type,
                        description=description or f"抓取 {source_name} 内容",
                        depends_on=depends_on,
                        input_payload={"fetcher_name": fetcher_name, "source_name": source_name, **input_payload},
                    )
                )
            elif task_type.startswith("tool.") or "search" in task_type:
                nodes.append(
                    {
                        "node_id": task_key,
                        "stage": "tool",
                        "component_name": "tool-calling-agent",
                        "depends_on": depends_on or [nodes[-1]["node_id"]] if nodes else ["fetch"],
                        "options": self._merge_tool_options(default_tool_options, input_payload, description),
                    }
                )
                tasks.append(
                    PlanTask(
                        task_key=task_key,
                        task_type="tool.execute",
                        description=description or "补充外部信息或执行工具查询",
                        depends_on=depends_on or ([nodes[-2]["node_id"]] if len(nodes) > 1 else ["fetch"]),
                        input_payload=dict(nodes[-1]["options"]),
                    )
                )
            elif task_type == "workflow.process" and self._looks_like_process_task(task_key, description, input_payload):
                has_process = True
                resolved_deps = depends_on or ([nodes[-1]["node_id"]] if nodes else ["fetch"])
                if insert_tool_before_process and not any(node["stage"] == "tool" for node in nodes):
                    tool_dep = nodes[-1]["node_id"] if nodes else "fetch"
                    nodes.append(
                        {
                            "node_id": "observation_tool",
                            "stage": "tool",
                            "component_name": "tool-calling-agent",
                            "depends_on": [tool_dep] if tool_dep else [],
                            "options": self._merge_tool_options(default_tool_options, {}, "根据 workflow 观测补充背景信息"),
                        }
                    )
                    tasks.append(
                        PlanTask(
                            task_key="observation_tool",
                            task_type="tool.execute",
                            description="根据 workflow 观测补充背景信息",
                            depends_on=[tool_dep] if tool_dep else [],
                            input_payload=dict(nodes[-1]["options"]),
                        )
                    )
                    resolved_deps = ["observation_tool"]
                nodes.append(
                    {
                        "node_id": task_key,
                        "stage": "process",
                        "component_name": str(input_payload.get("processor_name") or processor_name),
                        "depends_on": resolved_deps,
                        "options": {**process_options, **dict(input_payload.get("process_options") or {})},
                    }
                )
                tasks.append(
                    PlanTask(
                        task_key=task_key,
                        task_type=task_type,
                        description=description or f"处理内容并执行 {processor_name}",
                        depends_on=resolved_deps,
                        input_payload={"processor_name": processor_name, **input_payload},
                    )
                )
            elif task_type == "workflow.publish" and self._looks_like_publish_task(task_key, description, input_payload):
                has_publish = True
                resolved_deps = depends_on or ([nodes[-1]["node_id"]] if nodes else ["process"])
                nodes.append(
                    {
                        "node_id": task_key,
                        "stage": "publish",
                        "component_name": str(input_payload.get("publisher_name") or publisher_name),
                        "depends_on": resolved_deps,
                        "options": {**publish_options, **dict(input_payload.get("publish_options") or {})},
                    }
                )
                tasks.append(
                    PlanTask(
                        task_key=task_key,
                        task_type=task_type,
                        description=description or f"发布到 {publisher_name}",
                        depends_on=resolved_deps,
                        input_payload={"publisher_name": publisher_name, **input_payload},
                    )
                )

        if not has_fetch:
            nodes.insert(
                0,
                {
                    "node_id": "fetch",
                    "stage": "fetch",
                    "component_name": fetcher_name,
                    "options": fetch_options,
                },
            )
            tasks.insert(
                0,
                PlanTask(
                    task_key="fetch",
                    task_type="workflow.fetch",
                    description=f"抓取 {source_name} 内容",
                    input_payload={"fetcher_name": fetcher_name, "source_name": source_name},
                ),
            )
        if not has_process:
            if insert_tool_before_process and not any(node["stage"] == "tool" for node in nodes):
                tool_dep = nodes[-1]["node_id"] if nodes else "fetch"
                nodes.append(
                    {
                        "node_id": "observation_tool",
                        "stage": "tool",
                        "component_name": "tool-calling-agent",
                        "depends_on": [tool_dep] if tool_dep else [],
                        "options": self._merge_tool_options(default_tool_options, {}, "根据 workflow 观测补充背景信息"),
                    }
                )
                tasks.append(
                    PlanTask(
                        task_key="observation_tool",
                        task_type="tool.execute",
                        description="根据 workflow 观测补充背景信息",
                        depends_on=[tool_dep] if tool_dep else [],
                        input_payload=dict(nodes[-1]["options"]),
                    )
                )
            last_dep = nodes[-1]["node_id"] if nodes else "fetch"
            nodes.append(
                {
                    "node_id": "process",
                    "stage": "process",
                    "component_name": processor_name,
                    "depends_on": [last_dep] if last_dep != "process" else [],
                    "options": process_options,
                }
            )
            tasks.append(
                PlanTask(
                    task_key="process",
                    task_type="workflow.process",
                    description=f"处理内容并执行 {processor_name}",
                    depends_on=[last_dep] if last_dep != "process" else [],
                    input_payload={"processor_name": processor_name, "process_options": process_options},
                )
            )
        if not has_publish:
            last_dep = nodes[-1]["node_id"] if nodes else "process"
            nodes.append(
                {
                    "node_id": "publish",
                    "stage": "publish",
                    "component_name": publisher_name,
                    "depends_on": [last_dep] if last_dep != "publish" else [],
                    "options": publish_options,
                }
            )
            tasks.append(
                PlanTask(
                    task_key="publish",
                    task_type="workflow.publish",
                    description=f"发布到 {publisher_name}",
                    depends_on=[last_dep] if last_dep != "publish" else [],
                    input_payload={"publisher_name": publisher_name, "publish_options": publish_options},
                )
            )
        return nodes, tasks

    @staticmethod
    def _apply_memory_tuning(*, workflow_name: str, lookback_hours: int, limit: int) -> tuple[int, int, dict[str, Any]]:
        memory = AgentMemoryService().get_memory_value(
            scope="workflow",
            scope_key=workflow_name,
            memory_type="outcome",
            memory_key="last_run",
        )
        tuning = {"applied": False}
        if not isinstance(memory, dict):
            return lookback_hours, limit, tuning

        success_rate = float(memory.get("success_rate") or 0.0)
        if success_rate < 0.5:
            tuned_lookback = max(lookback_hours, int(memory.get("suggested_lookback_hours") or 48))
            tuned_limit = min(limit, int(memory.get("suggested_limit") or 10))
            return tuned_lookback, tuned_limit, {
                "applied": True,
                "reason": "low_success_rate",
                "success_rate": success_rate,
            }
        return lookback_hours, limit, tuning

    def _apply_observation_tuning(
        self,
        *,
        workflow_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        memory = AgentMemoryService().get_memory_value(
            scope="workflow",
            scope_key=workflow_name,
            memory_type="outcome",
            memory_key="last_run",
        )
        if not isinstance(memory, dict):
            return {
                "applied": False,
                "insert_tool_before_process": self._should_use_tool_stage("", context),
                "enable_quality_gate": False,
                "process_options": {},
                "observations": {},
            }

        observations = dict(memory.get("observations") or {})
        fetch_quality = dict(observations.get("fetch_quality") or {})
        tool_hit_rate = dict(observations.get("tool_hit_rate") or {})
        process_quality = dict(observations.get("process_quality") or {})
        review_failures = dict(observations.get("review_failure_reasons") or {})

        insert_tool_before_process = self._should_insert_tool_stage(fetch_quality, tool_hit_rate, context)
        enable_quality_gate = self._should_enable_quality_gate(process_quality, review_failures, context)
        process_options: dict[str, Any] = {}
        average_quality_score = float(process_quality.get("average_quality_score") or 0.0)
        if average_quality_score and average_quality_score < 0.7:
            process_options["rewrite_self_critique_rounds"] = 2
            process_options["rewrite_self_critique_threshold"] = 0.8

        return {
            "applied": bool(observations),
            "insert_tool_before_process": insert_tool_before_process,
            "enable_quality_gate": enable_quality_gate,
            "process_options": process_options,
            "observations": observations,
        }

    @staticmethod
    def _should_insert_tool_stage(
        fetch_quality: dict[str, Any],
        tool_hit_rate: dict[str, Any],
        context: dict[str, Any],
    ) -> bool:
        if bool(context.get("enable_tool_stage")):
            return True
        quality_score = float(fetch_quality.get("quality_score") or 0.0)
        attempts = int(tool_hit_rate.get("attempts") or 0)
        hit_rate = float(tool_hit_rate.get("hit_rate") or 0.0)
        return quality_score < 0.55 or (attempts > 0 and hit_rate < 0.5)

    @staticmethod
    def _should_enable_quality_gate(
        process_quality: dict[str, Any],
        review_failures: dict[str, Any],
        context: dict[str, Any],
    ) -> bool:
        if bool(context.get("enable_quality_gate")):
            return True
        average_quality_score = float(process_quality.get("average_quality_score") or 0.0)
        return average_quality_score < 0.7 or bool(review_failures.get("top_reasons"))

    @staticmethod
    def _build_next_run_suggestions(
        *,
        workflow_name: str,
        observation_tuning: dict[str, Any],
        memory_tuning: dict[str, Any],
    ) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        if observation_tuning.get("insert_tool_before_process"):
            suggestions.append(
                {
                    "workflow_name": workflow_name,
                    "action": "add_tool_context",
                    "reason": "fetch quality or tool hit rate indicates missing context",
                }
            )
        if observation_tuning.get("enable_quality_gate"):
            suggestions.append(
                {
                    "workflow_name": workflow_name,
                    "action": "enable_quality_gate",
                    "reason": "process quality or review failures indicate publish risk",
                }
            )
        if memory_tuning.get("applied"):
            suggestions.append(
                {
                    "workflow_name": workflow_name,
                    "action": "adjust_window",
                    "reason": str(memory_tuning.get("reason") or "memory tuning applied"),
                }
            )
        return suggestions

    @staticmethod
    def _merge_rewrite_preferences(process_options: dict[str, Any], preferences: dict[str, Any]) -> dict[str, Any]:
        merged = dict(process_options)
        if not preferences:
            return merged
        merged.setdefault("rewrite_preferences", {}).update(preferences)
        if preferences.get("voice"):
            merged.setdefault("preferred_voice", preferences.get("voice"))
        if preferences.get("tone"):
            merged.setdefault("preferred_tone", preferences.get("tone"))
        if preferences.get("length"):
            merged.setdefault("preferred_length", preferences.get("length"))
        if preferences.get("blocked_tags"):
            merged.setdefault("blocked_tags", preferences.get("blocked_tags"))
        return merged

    @staticmethod
    def _merge_tool_options(
        base: dict[str, Any],
        task_payload: dict[str, Any],
        description: str,
    ) -> dict[str, Any]:
        merged = dict(base)
        merged.update({key: value for key, value in task_payload.items() if key not in {"tool_calls", "tool_plan", "context"}})
        if task_payload.get("tool_calls"):
            merged["tool_calls"] = list(task_payload.get("tool_calls") or [])
        if task_payload.get("tool_plan"):
            merged["tool_plan"] = dict(task_payload.get("tool_plan") or {})
        if description and "intent_template" not in merged:
            merged["intent_template"] = description + "，参考抓取结果与上游输出。"
        merged.setdefault("merge_mode", "nested")
        merged.setdefault("result_key", str(task_payload.get("result_key") or merged.get("result_key") or "tool_context"))
        return merged

    @staticmethod
    def _looks_like_fetch_task(task_key: str, description: str, input_payload: dict[str, Any]) -> bool:
        text = f"{task_key} {description}".lower()
        return bool(input_payload.get("fetcher_name")) or any(keyword in text for keyword in ["fetch", "抓取", "source"])

    @staticmethod
    def _looks_like_process_task(task_key: str, description: str, input_payload: dict[str, Any]) -> bool:
        text = f"{task_key} {description}".lower()
        return bool(input_payload.get("processor_name")) or any(
            keyword in text for keyword in ["process", "处理", "改写", "摘要", "summarize", "rewrite"]
        )

    @staticmethod
    def _looks_like_publish_task(task_key: str, description: str, input_payload: dict[str, Any]) -> bool:
        text = f"{task_key} {description}".lower()
        return bool(input_payload.get("publisher_name")) or any(
            keyword in text for keyword in ["publish", "发布", "post", "blog", "markdown"]
        )

    @staticmethod
    def _resolve_fetcher(intent: str, context: dict[str, Any]) -> str:
        explicit = str(context.get("fetcher_name") or "").strip()
        if explicit:
            return explicit
        lowered = intent.lower()
        if "github" in lowered:
            return "github_trending"
        if "reddit" in lowered:
            return "reddit"
        if "rss" in lowered:
            return "rss"
        if "bilibili" in lowered or "b站" in lowered:
            return "bilibili"
        return "cnblogs"

    @staticmethod
    def _resolve_processor(intent: str) -> str:
        lowered = intent.lower()
        if "摘要" in intent or "summary" in lowered:
            return "summarize"
        return "rewrite"

    @staticmethod
    def _resolve_publisher(intent: str) -> str:
        lowered = intent.lower()
        if "digest" in lowered or "摘要" in intent or "日报" in intent:
            return "markdown"
        return "blog"

    @staticmethod
    def _should_use_tool_stage(intent: str, context: dict[str, Any]) -> bool:
        if bool(context.get("enable_tool_stage")):
            return True
        lowered = intent.lower()
        return any(keyword in lowered for keyword in ["search", "translate", "tool", "fact", "背景", "搜索", "翻译", "核查"])

    @staticmethod
    def _build_tool_options(intent: str, context: dict[str, Any]) -> dict[str, Any]:
        tool_plan = dict(context.get("tool_plan") or {})
        if tool_plan.get("steps"):
            return {
                "task_type": str(context.get("tool_task_type") or "tool.execute"),
                "tool_plan": tool_plan,
                "result_key": str(context.get("tool_result_key") or "tool_context"),
            }

        tool_calls = list(context.get("tool_calls") or [])
        if tool_calls:
            return {
                "task_type": str(context.get("tool_task_type") or "tool.execute"),
                "tool_calls": tool_calls,
                "result_key": str(context.get("tool_result_key") or "tool_context"),
            }

        lowered = intent.lower()
        if "translate" in lowered or "翻译" in intent:
            tool_calls = [
                {
                    "tool_name": "translate",
                    "parameters": {
                        "text": str(context.get("tool_text") or intent),
                        "target_lang": str(context.get("target_lang") or "zh-CN"),
                    },
                }
            ]
        else:
            tool_calls = [
                {
                    "tool_name": "web_search",
                    "parameters": {"query": str(context.get("search_query") or intent)},
                }
            ]
        return {
            "task_type": str(context.get("tool_task_type") or "tool.execute"),
            "tool_calls": tool_calls,
            "result_key": str(context.get("tool_result_key") or "tool_context"),
        }
