from __future__ import annotations

from apps.ai_processor.runtime.llm_client import MockProvider, OpenAICompatibleProvider
from apps.workflow_engine.registry.contracts import AIProcessorConfig, ContentAsset


def build_provider(config: AIProcessorConfig):
    if config.llm_provider == "local":
        return MockProvider()
    if config.llm_provider in {"openai", "anthropic"}:
        return OpenAICompatibleProvider(
            model=config.model,
            timeout=config.timeout_seconds,
        )
    return OpenAICompatibleProvider(
        model=config.model,
        timeout=config.timeout_seconds,
    )


def estimate_token_cost(*parts: str, enabled: bool = True) -> int:
    if not enabled:
        return 0
    text = "".join(part for part in parts if part)
    if not text:
        return 0
    return max(1, len(text) // 4)


def clone_content(content: ContentAsset) -> ContentAsset:
    return ContentAsset(
        content_id=content.content_id,
        source_type=content.source_type,
        source_id=content.source_id,
        title=content.title,
        raw_content=content.raw_content,
        processed_content=content.processed_content,
        source_url=content.source_url,
        metadata=dict(content.metadata),
    )


def fallback_summary(raw_content: str | None, limit: int = 200) -> str:
    text = (raw_content or "").strip()
    return text[:limit] if text else ""


def parse_title_and_content(text: str, fallback_title: str, fallback_content: str | None) -> tuple[str, str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return fallback_title, fallback_content or ""

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    rewritten_title = fallback_title
    rewritten_content = cleaned

    for line in lines:
        lower_line = line.lower()
        if lower_line.startswith("title:"):
            rewritten_title = line.split(":", 1)[1].strip() or fallback_title
        elif line.startswith("标题：") or line.startswith("标题:"):
            rewritten_title = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()
        elif lower_line.startswith("content:"):
            rewritten_content = line.split(":", 1)[1].strip() or (fallback_content or "")
        elif line.startswith("正文：") or line.startswith("正文:"):
            rewritten_content = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()

    if rewritten_content == cleaned and any(
        line.lower().startswith(("title:", "content:")) or line.startswith(("标题：", "标题:", "正文：", "正文:"))
        for line in lines
    ):
        content_lines = [
            line
            for line in lines
            if not line.lower().startswith(("title:", "content:")) and not line.startswith(("标题：", "标题:", "正文：", "正文:"))
        ]
        if content_lines:
            rewritten_content = "\n".join(content_lines)

    return rewritten_title, rewritten_content or (fallback_content or "")
