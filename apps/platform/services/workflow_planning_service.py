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

        fetch_options = dict(resolved_context.get("fetch_options") or {})
        process_options = dict(resolved_context.get("process_options") or {})
        publish_options = dict(resolved_context.get("publish_options") or {})
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
        should_use_tool = self._planner_requests_tool_stage(planner_plan) or self._should_use_tool_stage(intent, resolved_context)
        nodes, plan_tasks = self._build_nodes_and_tasks(
            source_name=source_name,
            fetcher_name=fetcher_name,
            processor_name=processor_name,
            publisher_name=publisher_name,
            fetch_options=fetch_options,
            process_options=process_options,
            publish_options=publish_options,
            should_use_tool=should_use_tool,
            tool_options=self._build_tool_options(intent, resolved_context),
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

    @staticmethod
    def _planner_requests_tool_stage(plan: dict[str, Any]) -> bool:
        for task in plan.get("tasks", []):
            task_type = str(task.get("task_type") or "").lower()
            if task_type.startswith("tool.") or "search" in task_type:
                return True
        return False

    @staticmethod
    def _build_nodes_and_tasks(
        *,
        source_name: str,
        fetcher_name: str,
        processor_name: str,
        publisher_name: str,
        fetch_options: dict[str, Any],
        process_options: dict[str, Any],
        publish_options: dict[str, Any],
        should_use_tool: bool,
        tool_options: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[PlanTask]]:
        nodes = [
            {
                "node_id": "fetch",
                "stage": "fetch",
                "component_name": fetcher_name,
                "options": fetch_options,
            }
        ]
        tasks = [
            PlanTask(
                task_key="fetch",
                task_type="workflow.fetch",
                description=f"抓取 {source_name} 内容",
                input_payload={"fetcher_name": fetcher_name, "source_name": source_name},
            )
        ]

        if should_use_tool:
            nodes.append(
                {
                    "node_id": "tool",
                    "stage": "tool",
                    "component_name": "tool-calling-agent",
                    "depends_on": ["fetch"],
                    "options": tool_options,
                }
            )
            tasks.append(
                PlanTask(
                    task_key="tool",
                    task_type="tool.execute",
                    description="补充外部信息或执行工具查询",
                    depends_on=["fetch"],
                    input_payload=tool_options,
                )
            )

        process_deps = [nodes[-1]["node_id"]]
        nodes.append(
            {
                "node_id": "process",
                "stage": "process",
                "component_name": processor_name,
                "depends_on": process_deps,
                "options": process_options,
            }
        )
        tasks.append(
            PlanTask(
                task_key="process",
                task_type="workflow.process",
                description=f"处理内容并执行 {processor_name}",
                depends_on=process_deps,
                input_payload={"processor_name": processor_name, "process_options": process_options},
            )
        )
        nodes.append(
            {
                "node_id": "publish",
                "stage": "publish",
                "component_name": publisher_name,
                "depends_on": ["process"],
                "options": publish_options,
            }
        )
        tasks.append(
            PlanTask(
                task_key="publish",
                task_type="workflow.publish",
                description=f"发布到 {publisher_name}",
                depends_on=["process"],
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
