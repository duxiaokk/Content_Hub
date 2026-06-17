from __future__ import annotations

from apps.ai_processor.runtime.base import BaseProcessor
from apps.ai_processor.runtime.helpers import build_provider, clone_content, estimate_token_cost, parse_title_and_content
from apps.workflow_engine.registry.contracts import ContentAsset, ProcessContext, ProcessResult


class RewriteProcessor(BaseProcessor):
    name = "rewrite"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        provider = build_provider(self.config)
        prompt_source = (content.raw_content or "").strip()
        if not prompt_source:
            return ProcessResult(content=content, status="skipped", warnings=["empty raw content"])

        system_prompt = str(
            context.options.get("rewrite_system_prompt")
            or "你是内容改写助手。请输出中文技术博客风格的标题和正文，保留事实、代码块和关键术语。"
        )
        user_prompt = (
            f"标题：{content.title}\n"
            f"来源：{content.source_type}\n"
            f"原文：\n{prompt_source}\n\n"
            "请输出以下格式：\n"
            "Title: 改写后的中文标题\n"
            "Content: 改写后的中文正文"
        )

        try:
            rewritten = await self._chat_with_fallback(provider, system_prompt, user_prompt)
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
                }
            )
            return ProcessResult(
                content=processed,
                status="processed",
                cost_tokens=estimate_token_cost(
                    system_prompt,
                    user_prompt,
                    rewritten,
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
