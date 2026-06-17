from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from apps.ai_processor.runtime.config import load_ai_processor_config
from apps.platform.models import RewriteProfile
from apps.workflow_engine.registry.contracts import AIProcessorConfig


@dataclass(slots=True)
class ResolvedRewriteProfile:
    name: str
    config: AIProcessorConfig
    system_prompt: str


def load_rewrite_profile(db_session: Session | None, profile_name: str | None = None) -> ResolvedRewriteProfile:
    base_config = load_ai_processor_config()
    resolved_name = profile_name or base_config.default_rewrite_profile

    if db_session is None:
        return ResolvedRewriteProfile(
            name=resolved_name,
            config=base_config,
            system_prompt=_default_system_prompt(),
        )

    row = db_session.query(RewriteProfile).filter(RewriteProfile.name == resolved_name).first()
    if row is None:
        return ResolvedRewriteProfile(
            name=resolved_name,
            config=base_config,
            system_prompt=_default_system_prompt(),
        )

    resolved_config = AIProcessorConfig(
        llm_provider=row.provider or base_config.llm_provider,
        model=row.model or base_config.model,
        max_tokens_per_call=row.max_tokens or base_config.max_tokens_per_call,
        timeout_seconds=row.timeout_seconds or base_config.timeout_seconds,
        fallback_strategy=row.fallback_strategy or base_config.fallback_strategy,
        enable_cost_tracking=base_config.enable_cost_tracking,
        default_rewrite_profile=resolved_name,
        rewrite_score_threshold=base_config.rewrite_score_threshold,
    )
    return ResolvedRewriteProfile(
        name=resolved_name,
        config=resolved_config,
        system_prompt=row.system_prompt or _default_system_prompt(),
    )


def _default_system_prompt() -> str:
    return (
        "你是技术内容改写助手。请将输入内容改写为中文技术博客风格，"
        "保留事实、代码块和关键术语，不要编造信息。"
    )
