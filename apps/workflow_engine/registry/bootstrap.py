from __future__ import annotations

from ai_processor.processors.rewrite.processor import RewriteProcessor
from fetcher_engine.connectors.bilibili.fetcher import BilibiliFetcher
from fetcher_engine.connectors.cnblogs.fetcher import CNBlogsFetcher
from publisher_engine.adapters.blog.publisher import BlogPublisher
from workflow_engine.registry.contracts import AIProcessorConfig
from workflow_engine.registry.settings import PipelineSettings
from workflow_engine.registry.static_registry import registry


def build_default_registry() -> None:
    settings = PipelineSettings()
    registry.register_fetcher(CNBlogsFetcher(feed_url=settings.cnblogs_feed_url))
    registry.register_fetcher(BilibiliFetcher(feed_url=settings.bilibili_feed_url))
    registry.register_processor(
        RewriteProcessor(
            AIProcessorConfig(
                llm_provider=settings.llm_provider,
                model=settings.llm_model,
                max_tokens_per_call=settings.llm_max_tokens_per_call,
                timeout_seconds=settings.llm_timeout_seconds,
                fallback_strategy=settings.llm_fallback_strategy,
                enable_cost_tracking=settings.llm_enable_cost_tracking,
            )
        )
    )
    registry.register_publisher(BlogPublisher())
