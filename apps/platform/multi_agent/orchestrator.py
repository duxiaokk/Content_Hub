"""Multi-Agent Orchestrator - 任务编排器。

将用户自然语言意图拆解为 Agent 协作 DAG，按依赖顺序调度执行，
收集结果并聚合返回。
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx

from apps.platform.multi_agent.agent_registry import AgentRegistry
from apps.platform.multi_agent.message_bus import MessageBus
from apps.platform.multi_agent.message_schemas import AgentMessage, OrchestrationResult
from apps.platform.multi_agent.plan_runtime import PlanRuntime, PlanRuntimeTask

logger = logging.getLogger(__name__)


class Orchestrator:
    """Multi-Agent 编排器。"""

    def __init__(
        self,
        message_bus: MessageBus | None = None,
        registry: AgentRegistry | None = None,
        planner_url: str | None = None,
        aggregator_url: str | None = None,
        internal_token: str = "local-dev-scheduler-token",
    ) -> None:
        self._bus = message_bus or MessageBus()
        self._registry = registry or AgentRegistry()
        self._internal_token = internal_token
        self._planner_url = planner_url or "http://127.0.0.1:8100"
        self._aggregator_url = aggregator_url or "http://127.0.0.1:8140"
        self._context: dict[str, Any] = {}

    async def execute(self, intent: str, context: dict[str, Any] | None = None) -> OrchestrationResult:
        """执行用户意图，返回最终结果。"""
        trace_id = str(uuid.uuid4())
        start_time = time.time()
        self._context = context or {}
        logger.info("[Orchestrator] trace_id=%s intent=%s", trace_id, intent)

        plan = await self._call_planner(intent, trace_id, self._context)
        if not plan or not plan.get("tasks"):
            logger.warning("[Orchestrator] Planner returned empty plan, trace_id=%s", trace_id)
            return OrchestrationResult(
                trace_id=trace_id,
                success=False,
                aggregated_result={},
                summary="Planner could not decompose the intent.",
                task_count=0,
                succeeded_count=0,
                failed_count=0,
                duration_seconds=round(time.time() - start_time, 2),
            )

        runtime = PlanRuntime.from_plan(plan)
        task_results: dict[str, dict[str, Any]] = {}

        async def executor(task: PlanRuntimeTask) -> dict[str, Any]:
            result = await self._execute_task(task, trace_id, task_results)
            task_results[task.task_key] = result
            return result

        task_results = await runtime.run(executor)
        tasks = runtime.tasks
        task_count = len(tasks)
        succeeded = runtime.count_by_status("succeeded")
        failed = runtime.count_by_status("failed")

        aggregated = await self._call_aggregator(trace_id, intent, tasks, task_results)
        duration = round(time.time() - start_time, 2)
        logger.info(
            "[Orchestrator] trace_id=%s done: success=%s tasks=%d succeeded=%d failed=%d duration=%.2fs",
            trace_id,
            aggregated.get("success"),
            task_count,
            succeeded,
            failed,
            duration,
        )

        return OrchestrationResult(
            trace_id=trace_id,
            success=aggregated.get("success", False) or succeeded > 0,
            aggregated_result=aggregated.get("aggregated_result", {}),
            summary=aggregated.get("summary", "No summary available"),
            task_count=task_count,
            succeeded_count=succeeded,
            failed_count=failed,
            duration_seconds=duration,
        )

    async def _call_planner(
        self,
        intent: str,
        trace_id: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """调用 PlannerAgent 拆解意图。"""
        agent = self._registry.find_agent_by_task_type("plan.decompose")
        url = agent.base_url if agent else self._planner_url

        payload = {
            "task_type": "plan.decompose",
            "trace_id": trace_id,
            "payload": {
                "intent": intent,
                "context": context or {},
                "available_capabilities": self._build_capability_list(),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{url}/api/internal/agent/run",
                    json=payload,
                    headers={"x-internal-token": self._internal_token},
                )
            resp.raise_for_status()
            return resp.json().get("result", {})
        except Exception as exc:
            logger.warning("[Orchestrator] Planner call failed: %s, using fallback plan", exc)
            return self._fallback_plan(intent)

    async def _execute_task(
        self,
        task: PlanRuntimeTask,
        trace_id: str,
        task_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """执行单个任务，通过 Message Bus 和 HTTP 调用 Agent。"""
        task_key = task.task_key
        task_type = task.task_type
        input_payload = dict(task.input_payload)

        for key, value in self._context.items():
            if key not in input_payload and value is not None:
                input_payload[key] = value

        for dep_key in task.depends_on:
            dep_result = task_results.get(dep_key, {})
            if dep_result.get("status") == "SUCCEEDED":
                input_payload.setdefault("_upstream_results", {})[dep_key] = dep_result.get("output", {})

        agent = self._registry.find_agent_by_task_type(task_type)
        if not agent:
            return {
                "status": "FAILED",
                "task_key": task_key,
                "error": f"No agent found for task_type: {task_type}",
            }

        self._bus.enqueue(
            AgentMessage(
                sender="orchestrator",
                recipient=agent.agent_key,
                message_type="task",
                payload={
                    "task_type": task_type,
                    "task_key": task_key,
                    "input_payload": input_payload,
                },
                trace_id=trace_id,
            )
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{agent.base_url}/api/internal/agent/run",
                    json={
                        "task_type": task_type,
                        "trace_id": trace_id,
                        "payload": input_payload,
                    },
                    headers={"x-internal-token": self._internal_token},
                )
            resp.raise_for_status()
            output = resp.json().get("result", {})
            self._bus.enqueue(
                AgentMessage(
                    sender=agent.agent_key,
                    recipient="orchestrator",
                    message_type="result",
                    payload={
                        "task_key": task_key,
                        "task_type": task_type,
                        "output": output,
                    },
                    trace_id=trace_id,
                )
            )
            return {"status": "SUCCEEDED", "task_key": task_key, "output": output}
        except Exception as exc:
            self._bus.enqueue(
                AgentMessage(
                    sender=agent.agent_key,
                    recipient="orchestrator",
                    message_type="error",
                    payload={
                        "task_key": task_key,
                        "task_type": task_type,
                        "error": str(exc),
                    },
                    trace_id=trace_id,
                )
            )
            return {"status": "FAILED", "task_key": task_key, "error": str(exc)}

    async def _call_aggregator(
        self,
        trace_id: str,
        intent: str,
        tasks: list[PlanRuntimeTask],
        task_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """调用 AggregatorAgent 聚合结果。"""
        agent = self._registry.find_agent_by_task_type("aggregate.merge")
        url = agent.base_url if agent else self._aggregator_url

        task_result_items = []
        for task in tasks:
            result = task_results.get(task.task_key, {})
            task_result_items.append(
                {
                    "task_key": task.task_key,
                    "task_type": task.task_type,
                    "status": result.get("status", "UNKNOWN"),
                    "output": result.get("output", {}),
                    "error": result.get("error"),
                }
            )

        payload = {
            "task_type": "aggregate.merge",
            "trace_id": trace_id,
            "payload": {
                "run_id": trace_id,
                "intent": intent,
                "task_results": task_result_items,
                "aggregation_mode": "merge",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{url}/api/internal/agent/run",
                    json=payload,
                    headers={"x-internal-token": self._internal_token},
                )
            resp.raise_for_status()
            return resp.json().get("result", {})
        except Exception as exc:
            logger.warning("[Orchestrator] Aggregator call failed: %s, using fallback merge", exc)
            return {
                "success": True,
                "aggregated_result": {"tasks": task_result_items},
                "summary": f"Aggregated {len(task_result_items)} tasks (fallback merge)",
            }

    def _build_capability_list(self) -> list[dict[str, Any]]:
        """为 Planner 构建当前可用能力列表。"""
        agents = self._registry.list_agents()
        return [
            {
                "agent_key": agent.agent_key,
                "task_types": agent.task_types,
                "capabilities": agent.capabilities,
            }
            for agent in agents
        ]

    def _fallback_plan(self, intent: str) -> dict[str, Any]:
        """当 Planner 不可用时，使用规则生成简单计划。"""
        intent_lower = intent.lower()
        tasks: list[dict[str, Any]] = []

        is_bilibili = any(
            keyword in intent_lower for keyword in ["b站", "bilibili", "哔哩哔哩", "up主", "uid"]
        )
        if is_bilibili:
            tasks.append(
                {
                    "task_key": "fetch",
                    "task_type": "bilibili.fetch.user",
                    "description": "Fetch Bilibili user videos",
                    "input_payload": {"intent": intent},
                }
            )
        elif any(keyword in intent_lower for keyword in ["抓取", "fetch", "获取", "采集", "collect"]):
            tasks.append(
                {
                    "task_key": "fetch",
                    "task_type": "tool.call",
                    "description": "Fetch data from source",
                    "input_payload": {"intent": intent},
                }
            )

        if any(keyword in intent_lower for keyword in ["分析", "analyze", "处理", "process", "统计"]):
            tasks.append(
                {
                    "task_key": "analyze",
                    "task_type": "data.process",
                    "description": "Process and analyze data",
                    "depends_on": ["fetch"] if tasks else [],
                    "input_payload": {"operation": "analyze"},
                }
            )

        if any(keyword in intent_lower for keyword in ["生成", "generate", "写作", "write", "摘要", "summary"]):
            deps = ["analyze"] if any(task["task_key"] == "analyze" for task in tasks) else ["fetch"] if tasks else []
            tasks.append(
                {
                    "task_key": "generate",
                    "task_type": "content.generate",
                    "description": "Generate content based on processed data",
                    "depends_on": deps,
                    "input_payload": {"topic": intent},
                }
            )

        if not tasks:
            tasks.append(
                {
                    "task_key": "generate",
                    "task_type": "content.generate",
                    "description": "Generate content",
                    "input_payload": {"topic": intent},
                }
            )

        return {
            "plan_id": str(uuid.uuid4()),
            "intent": intent,
            "tasks": tasks,
        }
