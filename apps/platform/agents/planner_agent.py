"""Planner Agent — 独立 FastAPI 服务

将用户的自然语言意图拆解为可执行的 DAG 计划。

任务类型: plan.decompose
输入:     intent + available_capabilities + context
输出:     tasks DAG + 依赖关系

启动:     python -m agents.planner_agent --port 8100
"""
from __future__ import annotations

import difflib
import json
import os
import uuid
from typing import Any

import httpx

from agents.base_agent import AgentConfig, BaseAgent

PLANNER_SYSTEM_PROMPT = """你是一个任务编排 Planner。请将用户意图分解为可执行的子任务 DAG。

## 输出格式（仅 JSON）
{
  "plan_id": "<uuid>",
  "intent": "<原始意图>",
  "tasks": [
    {
      "task_key": "唯一标识",
      "task_type": "从 capabilities 中选择",
      "description": "任务描述",
      "depends_on": ["依赖的 task_key"],
      "input_payload": {},
      "max_retries": 2,
      "retry_delay_seconds": 3.0,
      "estimated_tokens": 500,
      "estimated_duration_seconds": 5.0,
      "condition": null,
      "branch_on": {"success": "on_success_task_key", "failure": "on_failure_task_key"}
    }
  ]
}

## 拆解原则
1. 将复杂意图拆为 2-5 个子任务
2. 最大化并行度（减少不必要依赖）
3. task_type 必须从 available_capabilities 中选择
4. estimated_tokens 和 estimated_duration_seconds 给出合理估算
5. 若任务存在条件分支（condition 字段非空），使用 branch_on 标注成功/失败路径
6. 只输出 JSON，不要其他文字"""


class PlannerAgent(BaseAgent):
    """Planner Agent — 任务拆解。"""

    def supported_task_types(self) -> list[str]:
        return ["plan.decompose", "plan.complex_decompose"]

    async def execute(self, task_type: str, payload: dict[str, Any], trace_id: str | None) -> dict[str, Any]:
        intent = str(payload.get("intent", "")).strip()
        if not intent:
            raise ValueError("missing 'intent' in payload")

        context = payload.get("context", {}) if isinstance(payload.get("context"), dict) else {}
        constraints = payload.get("constraints", {}) if isinstance(payload.get("constraints"), dict) else {}
        capabilities = payload.get("available_capabilities", []) if isinstance(payload.get("available_capabilities"), list) else []

        is_complex = task_type == "plan.complex_decompose"

        if not self.config.mock_llm:
            return await self._plan_with_llm(intent, capabilities, context, constraints, is_complex)
        return self._plan_with_rules(intent, capabilities, context, is_complex)

    async def _plan_with_llm(self, intent: str, capabilities: list, context: dict, constraints: dict, is_complex: bool) -> dict:
        caps_text = json.dumps(capabilities, ensure_ascii=False)
        ctx_text = json.dumps(context, ensure_ascii=False, default=str)

        system_prompt = PLANNER_SYSTEM_PROMPT
        if is_complex:
            system_prompt += "\n\n## 复杂拆解模式\n你需要将意图进行多层嵌套拆解：每个子任务自身可能还包含子任务（sub_tasks）。深度 2-3 层。每层每个任务都需要包含 estimated_tokens 和 estimated_duration_seconds。"

        body = {
            "model": self.config.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"## 用户意图\n{intent}\n\n## 可用能力\n{caps_text}\n\n## 上下文\n{ctx_text}"},
            ],
            "temperature": 0.2,
            "max_tokens": 3000 if is_complex else 2000,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.config.llm_base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.config.llm_api_key}"},
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        plan = json.loads(self._extract_json(content))
        return self._post_process_plan(plan, capabilities)

    def _plan_with_rules(self, intent: str, capabilities: list, context: dict, is_complex: bool = False) -> dict:
        plan_id = str(uuid.uuid4())
        intent_lower = intent.lower()
        cap_types = {ct for c in capabilities for ct in (c.get("task_types", []))}

        tasks: list[dict] = []

        if any(kw in intent_lower for kw in ["生成", "draft", "generate", "create"]):
            gen_type = self._match_type_with_fallback(cap_types, ["generate_draft", "draft", "generate"])
            audit_type = self._match_type_with_fallback(cap_types, ["audit.draft", "audit", "review"])
            if gen_type:
                tasks.append({"task_key": "generate", "task_type": gen_type, "description": "内容生成", "input_payload": {}})
            if audit_type:
                deps = ["generate"] if gen_type else []
                tasks.append({"task_key": "audit", "task_type": audit_type, "description": "内容审核", "depends_on": deps})

        if any(kw in intent_lower for kw in ["分析", "analyze", "推荐", "recommend", "数据处理", "process"]):
            proc_type = self._match_type_with_fallback(cap_types, ["data.process", "data.extract", "transform"])
            analyze_type = self._match_type_with_fallback(cap_types, ["analyze_blog", "analyze", "ai.analyze"])
            if proc_type:
                tasks.append({"task_key": "process", "task_type": proc_type, "description": "数据处理"})
            if analyze_type:
                tasks.append({"task_key": "analyze", "task_type": analyze_type, "description": "数据分析"})

        if any(kw in intent_lower for kw in ["搜索", "search", "查找", "工具", "tool", "翻译", "translate"]):
            tool_type = self._match_type_with_fallback(cap_types, ["tool.call", "tool.execute", "search"])
            if tool_type:
                tasks.append({"task_key": "tool", "task_type": tool_type, "description": "工具调用"})

        if not tasks:
            default = list(cap_types)[0] if cap_types else "unknown"
            tasks.append({"task_key": "main", "task_type": default, "description": intent, "input_payload": {"intent": intent}})

        # --- 成本估算 & 条件分支 ---
        total_tokens = 0
        previous_task_key: str | None = None
        for i, task in enumerate(tasks):
            desc_len = len(task.get("description", ""))
            task["estimated_tokens"] = max(100, desc_len * 3 + 200)
            task["estimated_duration_seconds"] = max(1.0, round(desc_len * 0.02, 1))
            total_tokens += task["estimated_tokens"]

            # 条件分支：如果 payload 中指定了 condition
            if task.get("condition"):
                task.setdefault("branch_on", {"success": "_next_", "failure": "_retry_"})
                task.setdefault("max_retries", 3)
                task.setdefault("retry_delay_seconds", 5.0)

            if not task.get("depends_on") and previous_task_key:
                task.setdefault("depends_on", [previous_task_key])
            previous_task_key = task.get("task_key")

        # --- 复杂拆解：为每个子任务嵌入 sub_tasks ---
        if is_complex and len(tasks) > 1:
            for task in tasks:
                sub_intent = f"子任务: {task.get('description', '')}"
                sub_tasks = self._decompose_to_subtasks(sub_intent, cap_types)
                if sub_tasks:
                    task["sub_tasks"] = sub_tasks
                    for st in sub_tasks:
                        st["estimated_tokens"] = max(50, len(st.get("description", "")) * 3 + 100)
                        st["estimated_duration_seconds"] = max(0.5, round(len(st.get("description", "")) * 0.01, 1))
                        total_tokens += st["estimated_tokens"]

        return {
            "plan_id": plan_id,
            "intent": intent,
            "tasks": tasks,
            "estimated_duration_seconds": sum(t.get("estimated_duration_seconds", 5.0) for t in tasks),
            "estimated_total_tokens": total_tokens,
        }

    def _match_type(self, available: set, candidates: list[str]) -> str | None:
        """旧版精确匹配（保留以兼容）。"""
        for c in candidates:
            if c in available:
                return c
        for c in candidates:
            for a in available:
                if c in a or a in c:
                    return a
        return None

    def _fuzzy_match_type(self, target: str, available: set) -> str | None:
        """模糊匹配：当 task_type 未精确命中时，使用 difflib 找最接近的替代。"""
        if not available:
            return None
        avail_list = list(available)
        # 先尝试子串包含
        for a in avail_list:
            if target in a or a in target:
                return a
        # difflib 序列匹配
        best_ratio = 0.0
        best_match = None
        for a in avail_list:
            ratio = difflib.SequenceMatcher(None, target.lower(), a.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = a
        if best_match and best_ratio >= 0.4:
            return best_match
        # 返回第一个可用类型作为兜底
        return avail_list[0]

    def _match_type_with_fallback(self, available: set, candidates: list[str]) -> str | None:
        """精确匹配优先，未命中则对每个候选做模糊匹配。"""
        result = self._match_type(available, candidates)
        if result is not None:
            return result
        if not candidates:
            return None
        # 对每个候选尝试模糊匹配
        for c in candidates:
            fuzzy = self._fuzzy_match_type(c, available)
            if fuzzy:
                return fuzzy
        # 最终兜底：返回可用列表中的第一个
        return list(available)[0] if available else None

    def _post_process_plan(self, plan: dict, capabilities: list) -> dict:
        """对 LLM 输出的 plan 做后处理：补充成本估算、条件分支、模糊匹配回退。"""
        cap_types = {ct for c in capabilities for ct in (c.get("task_types", []))}
        total_tokens = 0
        for task in plan.get("tasks", []):
            # 成本估算
            desc_len = len(task.get("description", ""))
            task.setdefault("estimated_tokens", max(100, desc_len * 3 + 200))
            task.setdefault("estimated_duration_seconds", max(1.0, round(desc_len * 0.02, 1)))
            total_tokens += task["estimated_tokens"]

            # 自动回退：task_type 不在能力列表中时做模糊匹配
            tt = task.get("task_type", "")
            if tt and tt not in cap_types and cap_types:
                fallback = self._match_type_with_fallback(cap_types, [tt])
                if fallback:
                    task["task_type"] = fallback
                    task.setdefault("_original_task_type", tt)

            # 条件分支处理
            if task.get("condition"):
                task.setdefault("branch_on", {"success": "_next_", "failure": "_retry_"})
                task.setdefault("max_retries", 3)

            # 递归处理嵌套子任务
            for st in task.get("sub_tasks", []):
                st.setdefault("estimated_tokens", max(50, len(st.get("description", "")) * 3 + 100))
                st.setdefault("estimated_duration_seconds", max(0.5, round(len(st.get("description", "")) * 0.01, 1)))
                total_tokens += st["estimated_tokens"]

        plan.setdefault("estimated_duration_seconds", sum(
            t.get("estimated_duration_seconds", 5.0) for t in plan.get("tasks", [])
        ))
        plan["estimated_total_tokens"] = total_tokens
        return plan

    def _decompose_to_subtasks(self, intent: str, cap_types: set) -> list[dict]:
        """将单个任务进一步拆解为子任务列表（规则驱动）。"""
        intent_lower = intent.lower()
        subtasks: list[dict] = []

        if any(kw in intent_lower for kw in ["生成", "draft", "generate", "create"]):
            subtype = self._match_type_with_fallback(cap_types, ["generate_draft", "draft", "generate"])
            if subtype:
                subtasks.append({"task_key": "sub_generate", "task_type": subtype, "description": "子任务-生成", "depends_on": []})

        if any(kw in intent_lower for kw in ["审核", "audit", "review"]):
            subtype = self._match_type_with_fallback(cap_types, ["audit.draft", "audit", "review"])
            if subtype:
                deps = ["sub_generate"] if subtasks else []
                subtasks.append({"task_key": "sub_audit", "task_type": subtype, "description": "子任务-审核", "depends_on": deps})

        if any(kw in intent_lower for kw in ["分析", "analyze", "处理", "process"]):
            subtype = self._match_type_with_fallback(cap_types, ["data.process", "data.extract", "transform"])
            if subtype:
                subtasks.append({"task_key": "sub_process", "task_type": subtype, "description": "子任务-处理"})

        if not subtasks and intent_lower:
            default = list(cap_types)[0] if cap_types else "unknown"
            subtasks.append({"task_key": "sub_default", "task_type": default, "description": f"子任务: {intent[:30]}"})

        return subtasks

    def _extract_json(self, content: str) -> str:
        content = content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            parts = content.split("```")
            content = parts[1] if len(parts) > 1 else parts[0]
        return content


# =========================================================================
# 入口
# =========================================================================


def create_app():
    config = AgentConfig(
        agent_key=os.getenv("AGENT_KEY", "planner-agent"),
        agent_name=os.getenv("AGENT_NAME", "Planner Agent"),
        base_url=os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8100"),
        task_types=["plan.decompose", "plan.complex_decompose"],
        capabilities={"kind": "planner", "description": "任务拆解与编排规划"},
    )
    agent = PlannerAgent(config)
    return agent.create_app()


app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AGENT_PORT", "8100"))
    uvicorn.run("agents.planner_agent:app", host="0.0.0.0", port=port, reload=True)
