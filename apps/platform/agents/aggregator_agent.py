"""Aggregator Agent — 独立 FastAPI 服务

结果聚合 Agent：收集多 Agent 输出，聚合为统一结果。

任务类型: aggregate.merge, aggregate.summarize, aggregate.compose

模式:
  - merge:      简单合并各任务结果
  - summarize:  LLM 总结所有结果
  - compose:    将多结果组合为最终输出（如将大纲+分析+推荐合并为一篇文章）

输入:  run_id + task_results[]
输出:  aggregated_result

启动:     python -m agents.aggregator_agent --port 8140
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from agents.base_agent import AgentConfig, BaseAgent


AGGREGATOR_SUMMARIZE_PROMPT = """你是一个结果聚合器。将多个子任务结果汇总为最终输出。

要求：
1. 提取每个子任务的核心发现
2. 合并相似内容，去重
3. 输出结构化的 JSON 结果
4. 如果某子任务失败，标注但不影响整体
5. 只输出 JSON"""


class AggregatorAgent(BaseAgent):
    """Aggregator Agent — 结果聚合。"""

    def supported_task_types(self) -> list[str]:
        return ["aggregate.merge", "aggregate.summarize", "aggregate.compose", "aggregate.result"]

    async def execute(self, task_type: str, payload: dict[str, Any], trace_id: str | None) -> dict[str, Any]:
        run_id = str(payload.get("run_id", ""))
        intent = str(payload.get("intent", ""))
        task_results = payload.get("task_results", []) if isinstance(payload.get("task_results"), list) else []
        mode = str(payload.get("aggregation_mode", task_type.replace("aggregate.", "")))

        # --- 新功能参数 ---
        output_format = str(payload.get("output_format", "json")).lower()
        append_mode = bool(payload.get("append", False))
        existing = payload.get("existing_aggregation", {}) if isinstance(payload.get("existing_aggregation"), dict) else {}
        enable_confidence = bool(payload.get("enable_confidence", True))
        enable_conflict_resolution = bool(payload.get("enable_conflict_resolution", True))

        # --- 增量聚合 ---
        if append_mode and existing:
            return self._incremental_aggregate(run_id, task_results, existing, enable_confidence, enable_conflict_resolution)

        # --- 冲突检测与解决 ---
        if enable_conflict_resolution and len(task_results) > 1:
            task_results = self._resolve_conflicts(task_results)

        # --- 核心聚合 ---
        if mode == "summarize" and not self.config.mock_llm and self.config.llm_api_key:
            result = await self._summarize_with_llm(run_id, intent, task_results)
        elif mode == "compose":
            result = await self._compose(run_id, intent, task_results)
        else:
            result = self._merge(run_id, task_results)

        # --- 置信度评分 ---
        if enable_confidence:
            result = self._compute_confidence(result, task_results)

        # --- 格式转换 ---
        if output_format in ("markdown", "html", "json"):
            result = self._convert_format(result, output_format)

        return result

    async def _summarize_with_llm(self, run_id: str, intent: str, task_results: list[dict]) -> dict:
        successes = [r for r in task_results if r.get("status") == "SUCCEEDED"]
        if not successes:
            return {"run_id": run_id, "success": False, "aggregated_result": {}, "summary": "No successful tasks", "error": "All tasks failed"}

        results_text = json.dumps(
            [{"task_key": r.get("task_key", ""), "output": r.get("output", {})} for r in successes],
            ensure_ascii=False,
        )
        body = {
            "model": self.config.llm_model,
            "messages": [
                {"role": "system", "content": AGGREGATOR_SUMMARIZE_PROMPT},
                {"role": "user", "content": f"意图: {intent}\n\n任务结果:\n{results_text}"},
            ],
            "temperature": 0.3,
            "max_tokens": 1500,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.config.llm_base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.config.llm_api_key}"},
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            result = json.loads(self._extract_json(content))
        except json.JSONDecodeError:
            result = {"summary": content.strip()}

        return {"run_id": run_id, "success": True, "aggregated_result": result, "summary": result.get("summary", str(content)[:200])}

    def _merge(self, run_id: str, task_results: list[dict]) -> dict:
        merged = {"tasks": {}, "summary": ""}
        successes = 0
        for r in task_results:
            key = r.get("task_key", f"task_{len(merged['tasks'])}")
            merged["tasks"][key] = {
                "status": r.get("status", "UNKNOWN"),
                "output": r.get("output", {}),
                "error": r.get("error"),
            }
            if r.get("status") == "SUCCEEDED":
                successes += 1

        merged["summary"] = f"Completed {successes}/{len(task_results)} tasks"
        merged["total"] = len(task_results)
        merged["succeeded"] = successes
        merged["failed"] = len(task_results) - successes

        all_ok = all(r.get("status") == "SUCCEEDED" for r in task_results)
        return {"run_id": run_id, "success": all_ok or successes > 0, "aggregated_result": merged, "summary": merged["summary"]}

    async def _compose(self, run_id: str, intent: str, task_results: list[dict]) -> dict:
        """组合模式：将多个结果组合成一个统一输出。"""
        all_outputs: dict[str, Any] = {}
        for r in task_results:
            key = r.get("task_key", "")
            if r.get("status") == "SUCCEEDED" and r.get("output"):
                all_outputs[key] = r["output"]

        result = {
            "run_id": run_id,
            "success": True,
            "aggregated_result": {
                "composed": all_outputs,
                "tasks": {r.get("task_key", ""): r.get("status") for r in task_results},
            },
            "summary": f"Composed {len(all_outputs)} task outputs",
        }
        return result

    # =========================================================================
    # 置信度评分
    # =========================================================================

    def _compute_confidence(self, result: dict, task_results: list[dict]) -> dict:
        """为聚合结果中的每个 task_result 计算置信度分数 (0-1)。

        评分规则:
          - SUCCEEDED 且 output 非空: 0.95
          - SUCCEEDED 但 output 为空: 0.7
          - 状态带 "partial" / "degraded": 0.5
          - FAILED: 0.0
          - 其他状态按启发式计算
        聚合结果整体置信度取各任务置信度的加权平均。
        """
        scores: list[float] = []
        scored_tasks: dict[str, dict] = {}

        for r in task_results:
            key = r.get("task_key", f"task_{len(scores)}")
            status = (r.get("status") or "").upper()
            output = r.get("output") or {}
            error = r.get("error")
            artifact_ref = r.get("artifact_ref")

            # 基础分
            if status == "SUCCEEDED":
                base = 0.8
            elif "PARTIAL" in status or "DEGRADED" in status:
                base = 0.5
            elif status in ("FAILED", "CANCELED", "SKIPPED", "TIMED_OUT"):
                base = 0.0
            else:
                base = 0.3  # UNKNOWN / PENDING

            # 加分项
            bonus = 0.0
            if output and isinstance(output, dict) and len(output) > 0:
                bonus += 0.1
            if artifact_ref:
                bonus += 0.05
            if error is None:
                bonus += 0.05

            confidence = min(1.0, round(base + bonus, 2))
            scores.append(confidence)
            scored_tasks[key] = {
                "status": r.get("status"),
                "confidence": confidence,
                "confidence_breakdown": {
                    "base": base,
                    "bonus": bonus,
                    "has_output": bool(output and isinstance(output, dict) and len(output) > 0),
                    "has_artifact": bool(artifact_ref),
                    "no_error": error is None,
                },
            }

        # 聚合结果中附加置信度
        agg = result.get("aggregated_result", {})
        if isinstance(agg, dict):
            agg["confidence_scores"] = scored_tasks
            if scores:
                agg["overall_confidence"] = round(sum(scores) / len(scores), 2)
            else:
                agg["overall_confidence"] = 1.0

        return result

    # =========================================================================
    # 冲突解决
    # =========================================================================

    def _resolve_conflicts(self, task_results: list[dict]) -> list[dict]:
        """检测并解决同一 task_key 的多个结果之间的冲突。

        策略:
          1. 对相同 task_key 的多个结果，按成功优先选择
          2. 如果多个结果都成功但 output 不同，提取共同字段
          3. 对冲突字段按投票/多数原则合并
        """
        if not task_results:
            return task_results

        # 分组: task_key -> list of results
        grouped: dict[str, list[dict]] = {}
        for r in task_results:
            key = r.get("task_key", "unknown")
            grouped.setdefault(key, []).append(r)

        resolved: list[dict] = []
        for key, group in grouped.items():
            if len(group) == 1:
                resolved.append(group[0])
            else:
                resolved.append(self._conflict_voting(key, group))

        return resolved

    def _conflict_voting(self, task_key: str, group: list[dict]) -> dict:
        """对同一 task_key 的多个结果进行投票/多数决策。

        - 优先选择成功的
        - 相同成功级别时，合并非冲突字段
        - 冲突字段取出现次数最多的值（多数投票）
        """
        successes = [r for r in group if (r.get("status") or "").upper() == "SUCCEEDED"]
        if not successes:
            # 全失败 -> 取最后一个（最新）结果并标注
            result = dict(group[-1])
            result["conflict_resolution"] = {"method": "last_failed", "total": len(group), "succeeded": 0}
            return result

        if len(successes) == 1:
            result = dict(successes[0])
            result["conflict_resolution"] = {"method": "single_success", "total": len(group), "succeeded": 1}
            return result

        # 多个成功结果 -> 合并
        merged_output: dict[str, Any] = {}
        field_values: dict[str, list] = {}

        for s in successes:
            out = s.get("output", {}) if isinstance(s.get("output"), dict) else {}
            for f_name, f_val in out.items():
                field_values.setdefault(f_name, []).append(f_val)

        for f_name, values in field_values.items():
            # 统计每个值的出现次数
            counts: dict[str, int] = {}
            for v in values:
                v_key = str(v)
                counts[v_key] = counts.get(v_key, 0) + 1

            # 多数投票
            best_val_key = max(counts, key=counts.get)
            best_count = counts[best_val_key]
            total = len(values)

            if best_count > total / 2:
                # 绝对多数
                merged_output[f_name] = self._parse_val_key(best_val_key, values)
                merged_output.setdefault("_conflict_log", {})[f_name] = {
                    "resolved_by": "majority",
                    "votes": best_count,
                    "total": total,
                }
            elif best_count == total:
                # 完全一致
                merged_output[f_name] = values[0]
            else:
                # 相对多数或平局 -> 保留所有候选
                merged_output[f_name] = values[0]
                merged_output.setdefault("_conflict_log", {})[f_name] = {
                    "resolved_by": "plurality",
                    "votes": best_count,
                    "total": total,
                    "candidates": list(set(str(v) for v in values)),
                }

        result = {
            "task_key": task_key,
            "task_type": successes[0].get("task_type", group[0].get("task_type", "")),
            "status": "SUCCEEDED",
            "output": merged_output,
            "conflict_resolution": {
                "method": "voting",
                "total": len(group),
                "succeeded": len(successes),
                "conflict_fields": list(merged_output.get("_conflict_log", {}).keys()),
            },
        }
        return result

    @staticmethod
    def _parse_val_key(key: str, originals: list) -> Any:
        """将投票键还原为原始值类型。"""
        for v in originals:
            if str(v) == key:
                return v
        return key

    # =========================================================================
    # 格式转换
    # =========================================================================

    def _convert_format(self, result: dict, output_format: str) -> dict:
        """将聚合结果转换为指定格式。

        支持: json, markdown, html
        """
        agg = result.get("aggregated_result", {})

        if output_format == "json":
            # JSON 模式：确保聚合结果是纯 JSON 友好结构
            import json as _json
            result["formatted_output"] = _json.dumps(agg, ensure_ascii=False, indent=2, default=str)
            result["output_format"] = "json"
            return result

        if output_format == "markdown":
            md = self._render_markdown(agg)
            result["formatted_output"] = md
            result["output_format"] = "markdown"
            return result

        if output_format == "html":
            html = self._render_html(agg)
            result["formatted_output"] = html
            result["output_format"] = "html"
            return result

        # fallback: 返回原样
        return result

    def _render_markdown(self, aggregated: dict) -> str:
        """将聚合结果渲染为 Markdown。"""
        lines: list[str] = []
        summary = aggregated.get("summary", "")
        if summary:
            lines.append(f"## Summary\n\n{summary}\n")

        tasks = aggregated.get("tasks", {})
        if tasks:
            lines.append("## Tasks\n")
            for key, info in tasks.items():
                if isinstance(info, dict):
                    status = info.get("status", "UNKNOWN")
                    lines.append(f"### {key} ({status})\n")
                    output = info.get("output", {})
                    if output and isinstance(output, dict):
                        for k, v in output.items():
                            lines.append(f"- **{k}**: {v}")
                    error = info.get("error")
                    if error:
                        lines.append(f"- **Error**: {error}")
                    lines.append("")

        if "total" in aggregated:
            lines.append(f"**Total**: {aggregated['total']}  |  "
                         f"**Succeeded**: {aggregated.get('succeeded', 0)}  |  "
                         f"**Failed**: {aggregated.get('failed', 0)}")

        if "overall_confidence" in aggregated:
            lines.append(f"\n**Confidence**: {aggregated['overall_confidence']}")

        return "\n".join(lines)

    def _render_html(self, aggregated: dict) -> str:
        """将聚合结果渲染为 HTML。"""
        parts: list[str] = ['<div class="aggregation-result">']

        summary = aggregated.get("summary", "")
        if summary:
            parts.append(f"<h2>Summary</h2><p>{summary}</p>")

        tasks = aggregated.get("tasks", {})
        if tasks:
            parts.append("<h2>Tasks</h2>")
            for key, info in tasks.items():
                if isinstance(info, dict):
                    status = info.get("status", "UNKNOWN")
                    status_cls = status.lower()
                    parts.append(f'<div class="task task-{status_cls}">'
                                 f'<h3>{key} <span class="status">{status}</span></h3>')
                    output = info.get("output", {})
                    if output and isinstance(output, dict):
                        parts.append("<ul>")
                        for k, v in output.items():
                            parts.append(f"<li><strong>{k}</strong>: {v}</li>")
                        parts.append("</ul>")
                    error = info.get("error")
                    if error:
                        parts.append(f'<p class="error">{error}</p>')
                    parts.append("</div>")

        if "total" in aggregated:
            parts.append(f"<p class='stats'><strong>Total</strong>: {aggregated['total']} | "
                         f"<strong>Succeeded</strong>: {aggregated.get('succeeded', 0)} | "
                         f"<strong>Failed</strong>: {aggregated.get('failed', 0)}</p>")

        if "overall_confidence" in aggregated:
            parts.append(f"<p><strong>Confidence</strong>: {aggregated['overall_confidence']}</p>")

        parts.append("</div>")
        return "\n".join(parts)

    # =========================================================================
    # 增量聚合
    # =========================================================================

    def _incremental_aggregate(
        self,
        run_id: str,
        new_results: list[dict],
        existing: dict[str, Any],
        enable_confidence: bool,
        enable_conflict_resolution: bool,
    ) -> dict:
        """增量聚合：将新任务结果追加到已有聚合中。

        流程:
          1. 从 existing 中提取已有任务列表
          2. 合并新旧任务结果
          3. 可选冲突解决和置信度评分
          4. 重新计算统计
        """
        existing_tasks: dict[str, dict] = {}
        if isinstance(existing.get("aggregated_result"), dict):
            existing_tasks = existing["aggregated_result"].get("tasks", {})

        # 合并任务
        all_tasks: list[dict] = []
        existing_keys: set[str] = set()

        for key, info in existing_tasks.items():
            if isinstance(info, dict):
                existing_keys.add(key)
                all_tasks.append({
                    "task_key": key,
                    "status": info.get("status", "UNKNOWN"),
                    "output": info.get("output", {}),
                    "error": info.get("error"),
                })

        for nr in new_results:
            nk = nr.get("task_key", "")
            if nk in existing_keys:
                # 同 key 更新: 保留较新的（后面覆盖前面）
                for i, t in enumerate(all_tasks):
                    if t.get("task_key") == nk:
                        all_tasks[i] = nr
                        break
            else:
                all_tasks.append(nr)

        # 可选冲突解决
        if enable_conflict_resolution and len(all_tasks) > 1:
            all_tasks = self._resolve_conflicts(all_tasks)

        # 重新聚合
        merged = {"tasks": {}, "summary": "", "incremental": True}
        successes = 0
        for r in all_tasks:
            key = r.get("task_key", f"task_{len(merged['tasks'])}")
            merged["tasks"][key] = {
                "status": r.get("status", "UNKNOWN"),
                "output": r.get("output", {}),
                "error": r.get("error"),
            }
            if (r.get("status") or "").upper() == "SUCCEEDED":
                successes += 1

        merged["summary"] = f"Completed {successes}/{len(all_tasks)} tasks (incremental)"
        merged["total"] = len(all_tasks)
        merged["succeeded"] = successes
        merged["failed"] = len(all_tasks) - successes

        all_ok = successes == len(all_tasks) and len(all_tasks) > 0
        result = {"run_id": run_id, "success": all_ok or successes > 0,
                   "aggregated_result": merged, "summary": merged["summary"]}

        if enable_confidence:
            result = self._compute_confidence(result, all_tasks)

        return result

    # =========================================================================
    # JSON 提取
    # =========================================================================

    def _extract_json(self, content: str) -> str:
        content = content.strip()
        if "```json" in content:
            return content.split("```json")[1].split("```")[0]
        if "```" in content:
            return content.split("```")[1].split("```")[0]
        return content


# =========================================================================
# 入口
# =========================================================================


def create_app():
    config = AgentConfig(
        agent_key=os.getenv("AGENT_KEY", "aggregator-agent"),
        agent_name=os.getenv("AGENT_NAME", "Aggregator Agent"),
        base_url=os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8140"),
        task_types=["aggregate.merge", "aggregate.summarize", "aggregate.compose", "aggregate.result"],
        capabilities={"kind": "aggregator", "modes": ["merge", "summarize", "compose"]},
    )
    return AggregatorAgent(config).create_app()


app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AGENT_PORT", "8140"))
    uvicorn.run("agents.aggregator_agent:app", host="0.0.0.0", port=port, reload=True)
