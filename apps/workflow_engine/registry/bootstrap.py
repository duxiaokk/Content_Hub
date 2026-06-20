from __future__ import annotations

from apps.ai_processor.processors.classify.processor import ClassifyProcessor
from apps.ai_processor.processors.rewrite.processor import RewriteProcessor
from apps.ai_processor.processors.summarize.processor import SummarizeProcessor
from apps.ai_processor.processors.tag.processor import TagProcessor
from apps.fetcher_engine.connectors.bilibili.fetcher import BilibiliFetcher
from apps.fetcher_engine.connectors.cnblogs.fetcher import CNBlogsFetcher
from apps.fetcher_engine.connectors.github_trending.fetcher import GitHubTrendingFetcher
from apps.fetcher_engine.connectors.reddit.fetcher import RedditFetcher
from apps.fetcher_engine.connectors.xiaohongshu.fetcher import XiaohongshuFetcher
from apps.publisher_engine.adapters.blog.publisher import BlogPublisher
from apps.workflow_engine.registry.contracts import AIProcessorConfig
from apps.workflow_engine.registry.settings import PipelineSettings
from apps.workflow_engine.registry.static_registry import registry


def build_default_registry() -> None:
    settings = PipelineSettings()
    registry.register_fetcher(CNBlogsFetcher(feed_url=settings.cnblogs_feed_url))
    registry.register_fetcher(BilibiliFetcher(feed_url=settings.bilibili_feed_url))
    registry.register_fetcher(GitHubTrendingFetcher())
    registry.register_fetcher(RedditFetcher())
    registry.register_fetcher(XiaohongshuFetcher())
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
    registry.register_processor(
        SummarizeProcessor(
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
    registry.register_processor(
        ClassifyProcessor(
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
    registry.register_processor(
        TagProcessor(
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
