"""Aggregator Agent — 结果聚合

收集多 Agent 输出，聚合成统一结果。

输入:  AggregatorRequest  (run_id + task_results)
输出:  AggregatorResponse (aggregated_result)

策略:
  - 串联模式: 按 key 拼接各任务结果
  - 投票模式: 多个同类任务取多数结果
  - 总结模式: 调用 LLM 对结果做总结
"""
from __future__ import annotations

# Compatibility layer only.
# New aggregation capabilities should move to apps/platform/agents/aggregator_agent.py.

import json
from dataclasses import dataclass
from typing import Any

from scheduler_center.orchestration_schemas import (
    AggregatorRequest,
    AggregatorResponse,
    TaskResult,
)


AGGREGATOR_SYSTEM_PROMPT = """你是一个结果聚合器。请将多个子任务的结果汇总为最终输出。

要求：
1. 提取每个子任务的核心发现
2. 合并相似内容，去重
3. 输出结构化的 JSON 结果
4. 如果某子任务失败，标注但不影响整体
5. 只输出 JSON"""


@dataclass
class AggregatorConfig:
    mode: str = "merge"  # "merge" | "vote" | "summarize"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "deepseek-v4-flash"


class AggregatorAgent:
    """结果聚合 Agent。"""

    def __init__(self, config: AggregatorConfig | None = None) -> None:
        self._config = config or AggregatorConfig()

    def aggregate(self, request: AggregatorRequest) -> AggregatorResponse:
        """聚合多任务结果。"""
        successes = [r for r in request.task_results if r.status == "SUCCEEDED"]
        failures = [r for r in request.task_results if r.status == "FAILED"]

        if request.task_results and not successes and failures:
            errors = ", ".join(f"{f.task_key}: {f.error}" for f in failures)
            return AggregatorResponse(
                success=False,
                run_id=request.run_id,
                status="FAILED",
                error=f"All tasks failed: {errors}",
                trace_id=request.trace_id,
            )

        mode = self._config.mode
        if mode == "summarize":
            try:
                return self._aggregate_with_llm(request, successes)
            except Exception:
                mode = "merge"

        return self._aggregate_merge(request, successes)

    # ------------------------------------------------------------------
    # Merge 模式
    # ------------------------------------------------------------------

    def _aggregate_merge(self, request: AggregatorRequest, successes: list[TaskResult]) -> AggregatorResponse:
        """简单合并各任务结果。"""
        merged: dict[str, Any] = {"tasks": {}, "summary": ""}
        for r in request.task_results:
            merged["tasks"][r.task_key] = {
                "status": r.status,
                "output": r.output,
                "error": r.error,
            }

        # 生成简单摘要
        if successes:
            task_names = [s.task_key for s in successes]
            merged["summary"] = f"Successfully completed: {', '.join(task_names)}"
        merged["total"] = len(request.task_results)
        merged["succeeded"] = len(successes)
        merged["failed"] = len(request.task_results) - len(successes)

        return AggregatorResponse(
            success=True,
            run_id=request.run_id,
            status="SUCCEEDED" if not [r for r in request.task_results if r.status == "FAILED"] else "PARTIAL",
            aggregated_result=merged,
            summary=merged.get("summary"),
            trace_id=request.trace_id,
        )

    # ------------------------------------------------------------------
    # LLM 总结模式
    # ------------------------------------------------------------------

    def _aggregate_with_llm(self, request: AggregatorRequest, successes: list[TaskResult]) -> AggregatorResponse:
        import httpx

        results_text = json.dumps(
            [{"task_key": r.task_key, "output": r.output} for r in successes],
            ensure_ascii=False,
        )
        messages = [
            {"role": "system", "content": AGGREGATOR_SYSTEM_PROMPT},
            {"role": "user", "content": f"## 原始意图\n{request.intent}\n\n## 任务结果\n{results_text}"},
        ]

        body = {
            "model": self._config.llm_model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1500,
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
        try:
            summary_data = json.loads(content.strip().split("```json")[-1].split("```")[0])
        except json.JSONDecodeError:
            summary_data = {"raw": content}

        return AggregatorResponse(
            success=True,
            run_id=request.run_id,
            status="SUCCEEDED",
            aggregated_result=summary_data,
            summary=summary_data.get("summary", str(content)[:200]),
            trace_id=request.trace_id,
        )
