from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from apps.ai_processor.api.profiles import load_rewrite_profile
from apps.ai_processor.processors.classify.processor import ClassifyProcessor
from apps.ai_processor.processors.rewrite.processor import RewriteProcessor
from apps.ai_processor.processors.summarize.processor import SummarizeProcessor
from apps.ai_processor.processors.tag.processor import TagProcessor
from apps.platform.models import ContentItem
from apps.workflow_engine.registry.contracts import AIProcessorConfig, ContentAsset, ProcessContext, ProcessResult


class AIProcessingService:
    def __init__(self, db_session: Session, config: AIProcessorConfig) -> None:
        self.db_session = db_session
        self.config = config
        self.summarize_processor = SummarizeProcessor(config)
        self.classify_processor = ClassifyProcessor(config)
        self.tag_processor = TagProcessor(config)
        self.rewrite_processor = RewriteProcessor(config)

    async def process_content_item(self, content_item_id: int, context: ProcessContext) -> ProcessResult:
        item = self.db_session.query(ContentItem).filter(ContentItem.id == content_item_id).first()
        if item is None:
            raise ValueError(f"content item not found: {content_item_id}")

        asset = ContentAsset(
            content_id=item.id,
            source_type=item.source_type,
            source_id=item.source_id,
            title=item.title,
            raw_content=item.raw_content,
            processed_content=item.processed_content,
            source_url=item.source_url,
            metadata={},
        )

        summarize_result = await self.summarize_processor.process(asset, context)
        classify_result = await self.classify_processor.process(summarize_result.content, context)
        tag_result = await self.tag_processor.process(classify_result.content, context)

        summary = str(tag_result.content.metadata.get("summary") or "")
        tags = tag_result.content.metadata.get("tags") or []
        category = tag_result.content.metadata.get("category") or "其他"
        score = self._estimate_score(summary=summary, tags=tags, category=category)

        final_result = tag_result
        if score >= self.config.rewrite_score_threshold:
            profile = load_rewrite_profile(self.db_session, context.options.get("rewrite_profile"))
            rewrite_context = ProcessContext(
                run_id=context.run_id,
                options={
                    **dict(context.options),
                    "rewrite_system_prompt": profile.system_prompt,
                },
            )
            rewrite_processor = RewriteProcessor(profile.config)
            final_result = await rewrite_processor.process(tag_result.content, rewrite_context)

        item.summary = summary
        item.tags_json = json.dumps(tags, ensure_ascii=False)
        item.score = score
        item.rewritten_title = final_result.content.metadata.get("rewritten_title")
        item.rewritten_content = final_result.content.metadata.get("rewritten_content")
        item.pipeline_status = "processed"
        self.db_session.add(item)
        self.db_session.commit()
        self.db_session.refresh(item)

        final_asset = ContentAsset(
            content_id=item.id,
            source_type=item.source_type,
            source_id=item.source_id,
            title=str(final_result.content.metadata.get("rewritten_title") or item.title),
            raw_content=item.raw_content,
            processed_content=final_result.content.processed_content,
            source_url=item.source_url,
            metadata={
                "summary": summary,
                "tags": tags,
                "category": category,
                "score": score,
                "rewritten_title": item.rewritten_title,
                "rewritten_content": item.rewritten_content,
            },
        )
        return ProcessResult(
            content=final_asset,
            status=final_result.status if score >= self.config.rewrite_score_threshold else "processed",
            cost_tokens=(
                summarize_result.cost_tokens
                + classify_result.cost_tokens
                + tag_result.cost_tokens
                + (final_result.cost_tokens if score >= self.config.rewrite_score_threshold else 0)
            ),
        )

    def _estimate_score(self, *, summary: str, tags: list[str], category: str) -> float:
        score = 0.0
        if summary:
            score += min(len(summary) / 100, 3.0)
        score += min(len(tags), 5) * 0.8
        if category == "AI/LLM":
            score += 1.5
        return round(score, 2)
