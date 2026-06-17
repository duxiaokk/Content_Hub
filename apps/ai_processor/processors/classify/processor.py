from __future__ import annotations

from apps.ai_processor.runtime.base import BaseProcessor
from apps.ai_processor.runtime.helpers import build_provider, clone_content, estimate_token_cost
from apps.workflow_engine.registry.contracts import ContentAsset, ProcessContext, ProcessResult


RULE_CATEGORY_MAP = {
    "llm": "AI/LLM",
    "agent": "AI/LLM",
    "rag": "AI/LLM",
    "fastapi": "后端",
    "django": "后端",
    "react": "前端",
    "vue": "前端",
    "docker": "DevOps",
    "kubernetes": "DevOps",
    "security": "安全",
}


class ClassifyProcessor(BaseProcessor):
    name = "classify"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        del context
        title = (content.title or "").lower()
        summary = str(content.metadata.get("summary") or content.raw_content or "").lower()

        for keyword, category in RULE_CATEGORY_MAP.items():
            if keyword in title or keyword in summary:
                processed = clone_content(content)
                processed.metadata["category"] = category
                return ProcessResult(content=processed, status="processed", cost_tokens=0)

        provider = build_provider(self.config)
        system_prompt = "你是技术内容分类助手。只能从这些类别中选择一个：AI/LLM、前端、后端、DevOps、安全、其他。"
        user_prompt = f"标题：{content.title}\n摘要：{content.metadata.get('summary') or content.raw_content or ''}\n\n返回一个类别。"
        try:
            category = (await provider.chat(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=32)).strip()
            if category not in {"AI/LLM", "前端", "后端", "DevOps", "安全", "其他"}:
                category = "其他"
            processed = clone_content(content)
            processed.metadata["category"] = category
            return ProcessResult(
                content=processed,
                status="processed",
                cost_tokens=estimate_token_cost(system_prompt, user_prompt, category, enabled=self.config.enable_cost_tracking),
            )
        except Exception as exc:
            processed = clone_content(content)
            processed.metadata["category"] = "其他"
            processed.metadata["fallback_reason"] = str(exc)
            return ProcessResult(content=processed, status="fallback_raw", warnings=[str(exc)], cost_tokens=0)
