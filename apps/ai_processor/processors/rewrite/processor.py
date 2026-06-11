from __future__ import annotations

from ai_processor.runtime.base import BaseProcessor
from ai_processor.runtime.llm_client import MockProvider, OpenAICompatibleProvider
from workflow_engine.registry.contracts import ContentAsset, ProcessContext, ProcessResult


class RewriteProcessor(BaseProcessor):
    name = "rewrite"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        provider = self._build_provider()
        prompt_source = (content.raw_content or "").strip()
        if not prompt_source:
            return ProcessResult(content=content, status="skipped", warnings=["empty raw content"])

        system_prompt = (
            "你是内容改写助手。"
            "保持事实，不杜撰，不扩写无依据内容。"
            "输出适合技术博客发布的简体中文 Markdown。"
        )
        user_prompt = (
            f"标题：{content.title}\n"
            f"来源：{content.source_type}\n"
            f"原文：\n{prompt_source}\n\n"
            "请改写为一篇可发布的中文技术短文，保留核心信息，结构清晰。"
        )

        try:
            rewritten = await provider.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=self.config.max_tokens_per_call,
            )
            processed = ContentAsset(
                content_id=content.content_id,
                source_type=content.source_type,
                source_id=content.source_id,
                title=content.title,
                raw_content=content.raw_content,
                processed_content=rewritten.strip(),
                source_url=content.source_url,
                metadata={
                    **dict(content.metadata),
                    "llm_provider": self.config.llm_provider,
                    "llm_model": self.config.model,
                },
            )
            return ProcessResult(
                content=processed,
                status="processed",
                cost_tokens=self.config.max_tokens_per_call if self.config.enable_cost_tracking else 0,
            )
        except Exception as exc:
            fallback_content = content.raw_content if self.config.fallback_strategy in {"raw", "skip"} else None
            fallback_status = "fallback_raw" if self.config.fallback_strategy == "raw" else "skipped"
            if self.config.fallback_strategy == "retry":
                raise
            processed = ContentAsset(
                content_id=content.content_id,
                source_type=content.source_type,
                source_id=content.source_id,
                title=content.title,
                raw_content=content.raw_content,
                processed_content=fallback_content,
                source_url=content.source_url,
                metadata={
                    **dict(content.metadata),
                    "llm_provider": self.config.llm_provider,
                    "llm_model": self.config.model,
                    "fallback_reason": str(exc),
                },
            )
            return ProcessResult(
                content=processed,
                status=fallback_status,
                warnings=[str(exc)],
            )

    def _build_provider(self):
        if self.config.llm_provider == "local":
            return MockProvider()
        if self.config.llm_provider in {"openai", "anthropic"}:
            return OpenAICompatibleProvider(
                model=self.config.model,
                timeout=self.config.timeout_seconds,
            )
        return OpenAICompatibleProvider(
            model=self.config.model,
            timeout=self.config.timeout_seconds,
        )
