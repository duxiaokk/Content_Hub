"""Multi-Agent Orchestrator — 任务编排器。

将用户自然语言意图拆解为 Agent 协作 DAG，按依赖顺序调度执行，
收集结果并聚合返回。

核心流程:
    1. 用户 intent -> PlannerAgent -> DAG plan
    2. Orchestrator 按拓扑排序分发任务给各 Agent
    3. 每个 Agent 通过 HTTP 调用执行，结果写入 Message Bus
    4. 所有任务完成后 -> AggregatorAgent -> 最终报告

使用示例:
    orchestrator = Orchestrator()
    result = await orchestrator.execute("抓取 GitHub 并生成摘要")
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx

from apps.platform.multi_agent.agent_registry import AgentRegistry
from apps.platform.multi_agent.message_bus import MessageBus
from apps.platform.multi_agent.message_schemas import AgentMessage, OrchestrationResult

logger = logging.getLogger(__name__)

# 内置 planner 的模拟地址（实际环境中 PlannerAgent 应独立注册）
_PLANNER_AGENT_KEY = "planner-agent"
_TOOL_AGENT_KEY = "tool-calling-agent"
_DATA_AGENT_KEY = "data-processor-agent"
_CONTENT_AGENT_KEY = "content-generator-agent"
_AGGREGATOR_AGENT_KEY = "aggregator-agent"


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

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def execute(self, intent: str, context: dict[str, Any] | None = None) -> OrchestrationResult:
        """执行用户意图，返回最终结果。"""
        trace_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info("[Orchestrator] trace_id=%s intent=%s", trace_id, intent)

        # Step 1: Planner 拆解意图
        plan = await self._call_planner(intent, trace_id, context)
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

        tasks = plan["tasks"]
        task_count = len(tasks)
        logger.info("[Orchestrator] trace_id=%s plan tasks=%d", trace_id, task_count)

        # Step 2: 执行 DAG
        task_results: dict[str, dict[str, Any]] = {}
        succeeded = 0
        failed = 0

        # 拓扑排序执行（按依赖层级）
        executed: set[str] = set()
        while len(executed) < task_count:
            # 找出当前可执行的任务（依赖已满足）
            ready_tasks = [
                t for t in tasks
                if t["task_key"] not in executed
                and all(dep in executed for dep in t.get("depends_on", []))
            ]

            if not ready_tasks:
                # 有循环依赖，跳出
                logger.error("[Orchestrator] Circular dependency detected, trace_id=%s", trace_id)
                break

            # 并行执行 ready_tasks
            coros = [self._execute_task(t, trace_id, task_results) for t in ready_tasks]
            batch_results = await asyncio.gather(*coros, return_exceptions=True)

            for t, res in zip(ready_tasks, batch_results):
                key = t["task_key"]
                executed.add(key)
                if isinstance(res, Exception):
                    logger.error("[Orchestrator] task=%s failed: %s", key, res)
                    task_results[key] = {"status": "FAILED", "error": str(res)}
                    failed += 1
                else:
                    task_results[key] = res
                    if res.get("status") == "SUCCEEDED":
                        succeeded += 1
                    else:
                        failed += 1

        # Step 3: 聚合结果
        aggregated = await self._call_aggregator(
            trace_id, intent, tasks, task_results
        )

        duration = round(time.time() - start_time, 2)
        logger.info(
            "[Orchestrator] trace_id=%s done: success=%s tasks=%d succeeded=%d failed=%d duration=%.2fs",
            trace_id, aggregated.get("success"), task_count, succeeded, failed, duration,
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

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _call_planner(
        self, intent: str, trace_id: str, context: dict[str, Any] | None
    ) -> dict[str, Any]:
        """调用 PlannerAgent 拆解意图。"""
        # 先尝试从注册中心找到 PlannerAgent
        agent = self._registry.find_agent_by_task_type("plan.decompose")
        url = self._planner_url
        if agent:
            url = agent.base_url

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
            data = resp.json()
            result = data.get("result", {})
            # Planner 返回的是 plan 结构，直接返回
            return result
        except Exception as exc:
            logger.warning("[Orchestrator] Planner call failed: %s, using fallback plan", exc)
            # 降级：使用规则驱动的简单计划
            return self._fallback_plan(intent)

    async def _execute_task(
        self,
        task: dict[str, Any],
        trace_id: str,
        task_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """执行单个任务，通过 Message Bus 或直接 HTTP 调用 Agent。"""
        task_key = task["task_key"]
        task_type = task["task_type"]
        input_payload = dict(task.get("input_payload", {}))

        # 注入前置任务的结果作为上下文
        for dep_key in task.get("depends_on", []):
            dep_result = task_results.get(dep_key, {})
            if dep_result.get("status") == "SUCCEEDED":
                input_payload.setdefault("_upstream_results", {})[dep_key] = dep_result.get("output", {})

        # 查找 Agent
        agent = self._registry.find_agent_by_task_type(task_type)
        if not agent:
            return {
                "status": "FAILED",
                "task_key": task_key,
                "error": f"No agent found for task_type: {task_type}",
            }

        # 通过 Message Bus 发送任务
        msg = AgentMessage(
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
        self._bus.enqueue(msg)

        # 直接 HTTP 调用 Agent 执行（同步等待结果）
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
            data = resp.json()
            output = data.get("result", {})
            # 写入结果到 Message Bus
            result_msg = AgentMessage(
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
            self._bus.enqueue(result_msg)
            return {"status": "SUCCEEDED", "task_key": task_key, "output": output}
        except Exception as exc:
            error_msg = AgentMessage(
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
            self._bus.enqueue(error_msg)
            return {"status": "FAILED", "task_key": task_key, "error": str(exc)}

    async def _call_aggregator(
        self,
        trace_id: str,
        intent: str,
        tasks: list[dict],
        task_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """调用 AggregatorAgent 聚合结果。"""
        agent = self._registry.find_agent_by_task_type("aggregate.merge")
        url = self._aggregator_url
        if agent:
            url = agent.base_url

        task_result_items = []
        for t in tasks:
            key = t["task_key"]
            res = task_results.get(key, {})
            task_result_items.append({
                "task_key": key,
                "task_type": t["task_type"],
                "status": res.get("status", "UNKNOWN"),
                "output": res.get("output", {}),
                "error": res.get("error"),
            })

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
            data = resp.json()
            return data.get("result", {})
        except Exception as exc:
            logger.warning("[Orchestrator] Aggregator call failed: %s, using fallback merge", exc)
            # 降级：简单合并
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
                "agent_key": a.agent_key,
                "task_types": a.task_types,
                "capabilities": a.capabilities,
            }
            for a in agents
        ]

    def _fallback_plan(self, intent: str) -> dict[str, Any]:
        """当 Planner 不可用时，使用规则生成简单计划。"""
        intent_lower = intent.lower()
        tasks: list[dict] = []

        # 检测关键词，生成简单链式计划
        if any(k in intent_lower for k in ["抓取", "fetch", "获取", "采集", "collect"]):
            tasks.append({
                "task_key": "fetch",
                "task_type": "tool.call",
                "description": "Fetch data from source",
                "input_payload": {"intent": intent},
            })
        if any(k in intent_lower for k in ["分析", "analyze", "处理", "process", "统计"]):
            tasks.append({
                "task_key": "analyze",
                "task_type": "data.process",
                "description": "Process and analyze data",
                "depends_on": ["fetch"] if tasks else [],
                "input_payload": {"operation": "analyze"},
            })
        if any(k in intent_lower for k in ["生成", "generate", "写作", "write", "摘要", "summary"]):
            deps = ["analyze"] if any(t["task_key"] == "analyze" for t in tasks) else ["fetch"] if tasks else []
            tasks.append({
                "task_key": "generate",
                "task_type": "content.generate",
                "description": "Generate content based on processed data",
                "depends_on": deps,
                "input_payload": {"topic": intent},
            })

        if not tasks:
            # 默认：内容生成
            tasks.append({
                "task_key": "generate",
                "task_type": "content.generate",
                "description": "Generate content",
                "input_payload": {"topic": intent},
            })

        return {
            "plan_id": str(uuid.uuid4()),
            "intent": intent,
            "tasks": tasks,
        }
