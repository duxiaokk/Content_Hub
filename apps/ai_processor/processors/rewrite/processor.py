from __future__ import annotations

import re

from apps.ai_processor.runtime.base import BaseProcessor
from apps.ai_processor.runtime.helpers import build_provider, clone_content, estimate_token_cost, parse_title_and_content
from apps.workflow_engine.registry.contracts import ContentAsset, ProcessContext, ProcessResult


class RewriteProcessor(BaseProcessor):
    name = "rewrite"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        provider = build_provider(self.config)
        options = context.options if isinstance(context.options, dict) else {}
        prompt_source = (content.raw_content or "").strip()
        if not prompt_source:
            return ProcessResult(content=content, status="skipped", warnings=["empty raw content"])

        system_prompt = str(
            options.get("rewrite_system_prompt")
            or self._build_system_prompt(options)
        )
        workflow_observations = dict(options.get("workflow_observations") or {})
        process_quality = dict(workflow_observations.get("process_quality") or {})
        if float(process_quality.get("average_quality_score") or 1.0) < 0.7:
            options.setdefault("rewrite_self_critique_rounds", 2)
            options.setdefault("rewrite_self_critique_threshold", 0.8)
        user_prompt = (
            f"标题：{content.title}\n"
            f"来源：{content.source_type}\n"
            f"原文：\n{prompt_source}\n\n"
            "请输出以下格式：\n"
            "Title: 改写后的中文标题\n"
            "Content: 改写后的中文正文"
        )

        try:
            prompt_history: list[str] = []
            rewritten = await self._chat_with_fallback(provider, system_prompt, user_prompt)
            prompt_history.append(user_prompt)
            rewritten_title, rewritten_content = parse_title_and_content(
                rewritten,
                fallback_title=content.title,
                fallback_content=content.raw_content,
            )
            critique_attempts = 0
            critique_history: list[dict[str, object]] = []
            critique = {"score": 0.0, "passed": False, "feedback": "未执行质检"}
            retry_rounds = max(0, int(options.get("rewrite_self_critique_rounds", 1) or 0))
            total_rounds = max(1, retry_rounds + 1)
            threshold = float(options.get("rewrite_self_critique_threshold", 0.75) or 0.75)

            for round_index in range(total_rounds):
                critique_attempts = round_index + 1
                if options.get("enable_self_critique") is False:
                    critique = self._heuristic_assessment(content, rewritten_title, rewritten_content)
                else:
                    critique = await self._critique_rewrite(
                        provider=provider,
                        original=content,
                        rewritten_title=rewritten_title,
                        rewritten_content=rewritten_content,
                    )
                critique_history.append(
                    {
                        "round": round_index + 1,
                        "score": critique["score"],
                        "passed": critique["passed"],
                        "feedback": critique["feedback"],
                    }
                )
                if not self._should_retry_with_feedback(
                    options=options,
                    critique=critique,
                    round_index=round_index,
                    total_rounds=total_rounds,
                    threshold=threshold,
                ):
                    break
                feedback_prompt = self._build_feedback_prompt(user_prompt, critique["feedback"], round_index + 1)
                rewritten = await self._chat_with_fallback(provider, system_prompt, feedback_prompt)
                prompt_history.append(feedback_prompt)
                rewritten_title, rewritten_content = parse_title_and_content(
                    rewritten,
                    fallback_title=content.title,
                    fallback_content=content.raw_content,
                )

            processed = clone_content(content)
            processed.title = rewritten_title
            processed.processed_content = rewritten_content.strip()
            processed.metadata.update(
                {
                    "llm_provider": self.config.llm_provider,
                    "llm_model": self.config.model,
                    "rewritten_title": rewritten_title,
                    "rewritten_content": processed.processed_content,
                    "rewrite_critique_score": critique["score"],
                    "rewrite_critique_feedback": critique["feedback"],
                    "rewrite_critique_passed": critique["passed"],
                    "rewrite_attempts": critique_attempts,
                    "rewrite_critique_history": critique_history,
                }
            )
            return ProcessResult(
                content=processed,
                status="processed",
                cost_tokens=estimate_token_cost(
                    system_prompt,
                    "\n\n".join(prompt_history),
                    rewritten,
                    "\n".join(str(item["feedback"]) for item in critique_history),
                    enabled=self.config.enable_cost_tracking,
                ),
            )
        except Exception as exc:
            processed = clone_content(content)
            processed.metadata.update(
                {
                    "llm_provider": self.config.llm_provider,
                    "llm_model": self.config.model,
                    "fallback_reason": str(exc),
                }
            )
            if self.config.fallback_strategy == "raw":
                processed.metadata["rewritten_title"] = content.title
                processed.metadata["rewritten_content"] = content.raw_content
                processed.processed_content = content.raw_content
                status = "fallback_raw"
            else:
                status = "skipped"
            return ProcessResult(
                content=processed,
                status=status,
                warnings=[str(exc)],
            )

    async def _chat_with_fallback(self, provider, system_prompt: str, user_prompt: str) -> str:  # noqa: ANN001
        attempts = 2 if self.config.fallback_strategy == "retry" else 1
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                return await provider.chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=self.config.max_tokens_per_call,
                )
            except Exception as exc:  # pragma: no cover
                last_error = exc
        assert last_error is not None
        raise last_error

    async def _critique_rewrite(
        self,
        *,
        provider,
        original: ContentAsset,
        rewritten_title: str,
        rewritten_content: str,
    ) -> dict[str, object]:  # noqa: ANN001
        heuristic = self._heuristic_assessment(original, rewritten_title, rewritten_content)
        system_prompt = (
            "你是内容改写质检编辑。请检查改写结果是否保留事实、是否为中文技术博客风格、"
            "是否包含明显占位内容。只输出三行："
            "Score: 0到1之间的小数\nPass: yes/no\nFeedback: 一句话反馈"
        )
        user_prompt = (
            f"原标题：{original.title}\n"
            f"原文：\n{original.raw_content or ''}\n\n"
            f"改写标题：{rewritten_title}\n"
            f"改写正文：\n{rewritten_content}"
        )
        try:
            critique_text = await provider.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=256,
            )
        except Exception:
            return heuristic
        parsed = self._parse_critique_response(critique_text)
        if parsed is None:
            return heuristic
        if heuristic["score"] < parsed["score"]:
            parsed["score"] = heuristic["score"]
            if not heuristic["passed"] and heuristic["feedback"]:
                parsed["feedback"] = str(heuristic["feedback"])
                parsed["passed"] = False
        return parsed

    def _should_retry_with_feedback(
        self,
        *,
        options: dict[str, Any],
        critique: dict[str, object],
        round_index: int,
        total_rounds: int,
        threshold: float,
    ) -> bool:
        if options.get("enable_self_critique") is False:
            return False
        if round_index >= total_rounds - 1:
            return False
        score = float(critique.get("score") or 0.0)
        return (not bool(critique["passed"])) or score < threshold

    def _build_feedback_prompt(self, user_prompt: str, feedback: object, round_number: int) -> str:
        return (
            f"{user_prompt}\n\n"
            f"第 {round_number} 轮改写未通过质检，请根据以下反馈重新改写，并继续严格输出 Title/Content 格式：\n"
            f"{feedback}"
        )

    @staticmethod
    def _build_system_prompt(options: dict[str, Any]) -> str:
        preferences = dict(options.get("rewrite_preferences") or {})
        style_hints: list[str] = []
        if preferences.get("voice"):
            style_hints.append(f"文风偏好：{preferences['voice']}")
        if preferences.get("tone"):
            style_hints.append(f"语气偏好：{preferences['tone']}")
        if preferences.get("length"):
            style_hints.append(f"篇幅偏好：{preferences['length']}")
        blocked_tags = preferences.get("blocked_tags")
        if isinstance(blocked_tags, list) and blocked_tags:
            style_hints.append(f"避免提及标签：{', '.join(str(tag) for tag in blocked_tags)}")
        suffix = f"附加要求：{'；'.join(style_hints)}。" if style_hints else ""
        return (
            "你是内容改写助手。请输出中文技术博客风格的标题和正文，保留事实、代码块和关键术语。"
            f"{suffix}"
        )

    def _heuristic_assessment(
        self,
        original: ContentAsset,
        rewritten_title: str,
        rewritten_content: str,
    ) -> dict[str, object]:
        issues: list[str] = []
        content_text = (rewritten_content or "").strip()
        title_text = (rewritten_title or "").strip()
        original_text = (original.raw_content or "").strip()

        if not title_text:
            issues.append("标题为空")
        if not content_text:
            issues.append("正文为空")
        if "[mock mode]" in content_text.lower() or "simulated llm response" in content_text.lower():
            issues.append("正文仍包含占位输出")
        min_length = max(20, min(120, len(original_text) // 4 if original_text else 20))
        if len(content_text) < min_length:
            issues.append("正文过短，可能遗漏关键信息")
        if not re.search(r"[\u4e00-\u9fff]", f"{title_text}\n{content_text}"):
            issues.append("输出未体现中文改写风格")
        if "```" in original_text and "```" not in content_text:
            issues.append("原文代码块未保留")

        score = max(0.0, 1.0 - 0.25 * len(issues))
        return {
            "score": score,
            "passed": not issues,
            "feedback": "；".join(issues) if issues else "质量通过",
        }

    @staticmethod
    def _parse_critique_response(content: str) -> dict[str, object] | None:
        text = (content or "").strip()
        if not text:
            return None
        score_match = re.search(r"score\s*[:：]\s*([01](?:\.\d+)?)", text, re.IGNORECASE)
        pass_match = re.search(r"pass\s*[:：]\s*(yes|no|true|false)", text, re.IGNORECASE)
        feedback_match = re.search(r"feedback\s*[:：]\s*(.+)", text, re.IGNORECASE | re.DOTALL)
        if not score_match and not pass_match and not feedback_match:
            return None
        score = float(score_match.group(1)) if score_match else 0.0
        passed = pass_match.group(1).lower() in {"yes", "true"} if pass_match else score >= 0.75
        feedback = feedback_match.group(1).strip() if feedback_match else ("质量通过" if passed else "需要改进")
        return {"score": score, "passed": passed, "feedback": feedback}
