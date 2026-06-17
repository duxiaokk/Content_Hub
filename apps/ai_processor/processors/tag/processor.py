from __future__ import annotations

from apps.ai_processor.runtime.base import BaseProcessor
from apps.ai_processor.runtime.helpers import build_provider, clone_content, estimate_token_cost
from apps.workflow_engine.registry.contracts import ContentAsset, ProcessContext, ProcessResult


RULE_TAGS = ["Python", "FastAPI", "SQLAlchemy", "Agent", "RAG", "Docker", "Kubernetes", "React", "Vue", "Go"]


class TagProcessor(BaseProcessor):
    name = "tag"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        del context
        source_text = f"{content.title} {content.metadata.get('summary') or content.raw_content or ''}".lower()
        matched_tags = [tag for tag in RULE_TAGS if tag.lower() in source_text]
        if matched_tags:
            processed = clone_content(content)
            processed.metadata["tags"] = matched_tags[:5]
            return ProcessResult(content=processed, status="processed", cost_tokens=0)

        provider = build_provider(self.config)
        system_prompt = "你是技术标签助手。请输出3到5个技术标签，使用英文逗号分隔，不要解释。"
        user_prompt = f"标题：{content.title}\n摘要：{content.metadata.get('summary') or content.raw_content or ''}\n\n请输出标签。"
        try:
            raw_tags = (await provider.chat(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=64)).strip()
            tags = [tag.strip() for tag in raw_tags.replace("，", ",").split(",") if tag.strip()][:5]
            processed = clone_content(content)
            processed.metadata["tags"] = tags
            return ProcessResult(
                content=processed,
                status="processed",
                cost_tokens=estimate_token_cost(system_prompt, user_prompt, raw_tags, enabled=self.config.enable_cost_tracking),
            )
        except Exception as exc:
            processed = clone_content(content)
            processed.metadata["tags"] = []
            processed.metadata["fallback_reason"] = str(exc)
            return ProcessResult(content=processed, status="fallback_raw", warnings=[str(exc)], cost_tokens=0)
