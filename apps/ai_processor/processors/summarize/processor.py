from __future__ import annotations

from apps.ai_processor.runtime.base import BaseProcessor
from apps.ai_processor.runtime.helpers import build_provider, clone_content, estimate_token_cost, fallback_summary
from apps.workflow_engine.registry.contracts import ContentAsset, ProcessContext, ProcessResult


class SummarizeProcessor(BaseProcessor):
    name = "summarize"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        del context
        provider = build_provider(self.config)
        prompt_source = (content.raw_content or "").strip()
        if not prompt_source:
            processed = clone_content(content)
            processed.metadata["summary"] = ""
            return ProcessResult(content=processed, status="skipped", warnings=["empty raw content"])

        system_prompt = "你是技术内容摘要助手。请输出不超过200字的简体中文摘要，只保留关键信息。"
        user_prompt = f"标题：{content.title}\n来源：{content.source_type}\n正文：\n{prompt_source}\n\n请生成摘要。"

        try:
            summary = (await provider.chat(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=256)).strip()
            processed = clone_content(content)
            processed.metadata["summary"] = summary
            return ProcessResult(
                content=processed,
                status="processed",
                cost_tokens=estimate_token_cost(system_prompt, user_prompt, summary, enabled=self.config.enable_cost_tracking),
            )
        except Exception as exc:
            summary = fallback_summary(content.raw_content, limit=200)
            processed = clone_content(content)
            processed.metadata["summary"] = summary
            processed.metadata["fallback_reason"] = str(exc)
            return ProcessResult(
                content=processed,
                status="fallback_raw",
                warnings=[str(exc)],
                cost_tokens=0,
            )
