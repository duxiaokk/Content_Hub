"""Planner Agent — 任务拆解

将用户的自然语言意图拆解为可执行的 DAG 计划。

输入:  PlannerRequest  (intent + capabilities + context)
输出:  ExecutionPlan   (DAG 中的 task 列表)

策略:
  1. LLM 模式: 调用 LLM 解析意图，生成结构化计划 (完整)
  2. 规则模式: 基于关键字匹配预设模板，生成计划 (降级)
  3. 静态模式: 直接接受预定义 plan，不做拆解
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from scheduler_center.orchestration_schemas import (
    AgentCapability,
    ExecutionPlan,
    PlannerRequest,
    PlannerResponse,
    PlanTask,
)


PLANNER_SYSTEM_PROMPT = """你是一个任务编排 Planner。你的职责是将用户的自然语言意图分解为可并行执行的任务 DAG。

## 输入
你会收到:
- intent: 用户需求
- context: 上下文数据
- available_capabilities: 可用 Agent 能力列表（每个能力有 task_type 和 description）

## 输出要求
返回 JSON，格式为：
{
  "tasks": [
    {
      "task_key": "唯一任务标识",
      "task_type": "对应 capability 中的 task_type",
      "description": "任务描述",
      "depends_on": ["依赖的 task_key 列表"],
      "input_payload": {"传给 Agent 的参数"},
      "max_retries": 2,
      "retry_delay_seconds": 3.0
    }
  ]
}

## 拆解原则
1. 将复杂意图拆为 2-5 个子任务
2. 子任务之间尽量解耦，最大化并行度
3. depends_on 只标记真正有数据依赖的任务
4. task_type 必须从 available_capabilities 中选择
5. 如果无法拆解，创建一个 single task
6. 只输出 JSON，不要任何其他文字
"""


def _build_planning_prompt(intent: str, capabilities_desc: str, context_desc: str) -> str:
    return f"""## 用户意图
{intent}

## 可用 Agent 能力
{capabilities_desc}

## 上下文
{context_desc}

请输出拆解后的任务计划（仅 JSON）："""


@dataclass
class PlannerConfig:
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "deepseek-v4-flash"
    use_mock: bool = True


class PlannerAgent:
    """Planner Agent — 任务拆解器。"""

    def __init__(self, config: PlannerConfig | None = None) -> None:
        self._config = config or PlannerConfig()

    def plan(self, request: PlannerRequest) -> PlannerResponse:
        """根据意图生成执行计划。"""
        plan_id = str(uuid.uuid4())
        trace_id = request.trace_id or str(uuid.uuid4())

        capabilities = request.available_capabilities
        if not capabilities:
            return PlannerResponse(
                success=False,
                error="No available capabilities provided",
                trace_id=trace_id,
            )

        # 优先 LLM，降级 Rule-based
        try:
            if not self._config.use_mock:
                return self._plan_with_llm(request, plan_id, trace_id)
        except Exception:
            pass

        return self._plan_with_rules(request, plan_id, trace_id)

    # ------------------------------------------------------------------
    # LLM 拆解
    # ------------------------------------------------------------------

    def _plan_with_llm(self, request: PlannerRequest, plan_id: str, trace_id: str) -> PlannerResponse:
        import httpx

        caps_desc = json.dumps(
            [{"task_type": c.task_types, "description": c.description} for c in request.available_capabilities],
            ensure_ascii=False,
        )
        context_desc = json.dumps(request.context, ensure_ascii=False, default=str)

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": _build_planning_prompt(request.intent, caps_desc, context_desc)},
        ]

        body = {
            "model": self._config.llm_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2000,
        }
        headers = {"Authorization": f"Bearer {self._config.llm_api_key}"}

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self._config.llm_base_url}/chat/completions",
                json=body,
                headers=headers,
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        plan_data = self._parse_llm_response(content)

        tasks = self._validate_and_build_tasks(plan_data, request)
        return PlannerResponse(
            success=True,
            plan=ExecutionPlan(plan_id=plan_id, intent=request.intent, tasks=tasks, trace_id=trace_id),
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # Rule-based 降级拆解
    # ------------------------------------------------------------------

    def _plan_with_rules(self, request: PlannerRequest, plan_id: str, trace_id: str) -> PlannerResponse:
        """基于关键字匹配的规则拆解。"""
        intent_lower = request.intent.lower()
        caps = {ct for c in request.available_capabilities for ct in c.task_types}

        tasks: list[PlanTask] = []

        # 模式 1: "生成 + 审核" → 串行
        if any(kw in intent_lower for kw in ["生成", "draft", "create", "generate"]):
            generate_type = self._find_task_type(caps, ["draft", "generate", "outline"])
            audit_type = self._find_task_type(caps, ["audit", "review", "moderate"])
            if generate_type:
                tasks.append(PlanTask(task_key="generate", task_type=generate_type, description="内容生成"))
            if audit_type:
                deps = ["generate"] if generate_type else []
                tasks.append(PlanTask(task_key="audit", task_type=audit_type, description="内容审核", depends_on=deps))

        # 模式 2: "分析 + 推荐" → 并行
        if any(kw in intent_lower for kw in ["分析", "analyze", "推荐", "recommend"]):
            analyze_type = self._find_task_type(caps, ["analyze"])
            recommend_type = self._find_task_type(caps, ["recommend"])
            if analyze_type:
                tasks.append(PlanTask(task_key="analyze", task_type=analyze_type, description="平台分析"))
            if recommend_type:
                tasks.append(PlanTask(task_key="recommend", task_type=recommend_type, description="选题推荐"))

        # 模式 3: "搬运/同步" + "审核" → 串行
        if any(kw in intent_lower for kw in ["搬运", "搬运", "repost", "同步", "sync"]):
            repost_type = self._find_task_type(caps, ["repost", "run", "sync"])
            audit_type = self._find_task_type(caps, ["audit", "review"])
            if repost_type:
                tasks.append(PlanTask(task_key="repost", task_type=repost_type, description="内容搬运"))
            if audit_type:
                deps = ["repost"] if repost_type else []
                tasks.append(PlanTask(task_key="audit", task_type=audit_type, description="内容审核", depends_on=deps))

        # 默认: 单任务
        if not tasks:
            default_type = self._find_task_type(caps, list(caps))
            if default_type:
                tasks.append(PlanTask(task_key="main_task", task_type=default_type, description=request.intent))

        return PlannerResponse(
            success=True,
            plan=ExecutionPlan(plan_id=plan_id, intent=request.intent, tasks=tasks, trace_id=trace_id),
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _find_task_type(self, caps: set[str], candidates: list[str]) -> str | None:
        for c in candidates:
            if c in caps:
                return c
        # 部分匹配
        for c in candidates:
            for cap in caps:
                if c in cap or cap in c:
                    return cap
        return None

    def _parse_llm_response(self, content: str) -> dict[str, Any]:
        content = content.strip()
        # 提取 JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 尝试提取 { }
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                return json.loads(content[start:end + 1])
        return {}

    def _validate_and_build_tasks(self, plan_data: dict, request: PlannerRequest) -> list[PlanTask]:
        raw_tasks = plan_data.get("tasks", [])
        if not isinstance(raw_tasks, list):
            raw_tasks = [raw_tasks] if isinstance(raw_tasks, dict) else []

        valid_task_types = {ct for c in request.available_capabilities for ct in c.task_types}
        tasks: list[PlanTask] = []
        seen_keys: set[str] = set()

        for i, t in enumerate(raw_tasks):
            task_key = str(t.get("task_key", f"task_{i}"))
            if task_key in seen_keys:
                task_key = f"{task_key}_{i}"
            seen_keys.add(task_key)

            task_type = str(t.get("task_type", ""))
            if task_type not in valid_task_types and valid_task_types:
                # 尝试匹配
                task_type = self._find_task_type(valid_task_types, [task_type]) or task_type

            depends_on = [str(d) for d in t.get("depends_on", []) if isinstance(d, (str, int))]

            tasks.append(PlanTask(
                task_key=task_key,
                task_type=task_type,
                description=str(t.get("description", "")),
                depends_on=depends_on,
                input_payload=t.get("input_payload", {}) if isinstance(t.get("input_payload"), dict) else {},
                max_retries=int(t.get("max_retries", 2)),
                retry_delay_seconds=float(t.get("retry_delay_seconds", 3.0)),
            ))

        return tasks
