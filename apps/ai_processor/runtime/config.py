from __future__ import annotations

import os

from apps.workflow_engine.registry.contracts import AIProcessorConfig


def load_ai_processor_config() -> AIProcessorConfig:
    return AIProcessorConfig(
        llm_provider=os.getenv("CONTENT_HUB_LLM_PROVIDER", "openai"),
        model=os.getenv("CONTENT_HUB_LLM_MODEL", "gpt-4.1-mini"),
        max_tokens_per_call=int(os.getenv("CONTENT_HUB_LLM_MAX_TOKENS", "2048")),
        timeout_seconds=int(os.getenv("CONTENT_HUB_LLM_TIMEOUT_SECONDS", "60")),
        fallback_strategy=os.getenv("CONTENT_HUB_LLM_FALLBACK", "skip"),
        enable_cost_tracking=os.getenv("CONTENT_HUB_LLM_COST_TRACKING", "true").lower() in {"1", "true", "yes", "on"},
        default_rewrite_profile=os.getenv("CONTENT_HUB_DEFAULT_REWRITE_PROFILE", "zh_tech_blog"),
        rewrite_score_threshold=float(os.getenv("CONTENT_HUB_REWRITE_SCORE_THRESHOLD", "0.5")),
    )
