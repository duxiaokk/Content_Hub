from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class PipelineSettings:
    cnblogs_feed_url: str = os.getenv(
        "CONTENT_HUB_CNBLOGS_FEED_URL",
        "https://feed.cnblogs.com/blog/u/126286/rss",
    )
    bilibili_feed_url: str = os.getenv(
        "CONTENT_HUB_BILIBILI_FEED_URL",
        "https://rsshub.app/bilibili/user/video/2267573",
    )
    llm_provider: str = os.getenv("CONTENT_HUB_LLM_PROVIDER", "openai")
    llm_model: str = os.getenv("CONTENT_HUB_LLM_MODEL", "gpt-4.1-mini")
    llm_max_tokens_per_call: int = int(os.getenv("CONTENT_HUB_LLM_MAX_TOKENS", "4000"))
    llm_timeout_seconds: int = int(os.getenv("CONTENT_HUB_LLM_TIMEOUT_SECONDS", "60"))
    llm_fallback_strategy: str = os.getenv("CONTENT_HUB_LLM_FALLBACK", "raw")
    llm_enable_cost_tracking: bool = os.getenv("CONTENT_HUB_LLM_COST_TRACKING", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
