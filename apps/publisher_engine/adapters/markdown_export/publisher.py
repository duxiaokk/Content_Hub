from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.publisher_engine.runtime.models import DigestPublishResult
from apps.publisher_engine.runtime.settings import PublisherSettings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarkdownDigestPublisher:
    name = "markdown_digest"

    async def publish(self, items: list[dict], options: dict | None = None) -> dict[str, Any]:
        resolved_options = dict(options or {})
        settings = PublisherSettings()
        now = _utcnow()
        output_dir = Path(resolved_options.get("output_dir") or settings.digest_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        date_str = now.strftime("%Y-%m-%d")
        file_path = output_dir / f"{date_str}.md"
        markdown = self._build_markdown(items, now=now)
        file_path.write_text(markdown, encoding="utf-8")

        result = DigestPublishResult(
            title=f"技术内容日报 - {date_str}",
            content_markdown=markdown,
            file_path=str(file_path),
            included_count=len(items),
            generated_at=now.isoformat(),
        )
        return result.to_dict()

    def _build_markdown(self, items: list[dict], *, now: datetime) -> str:
        lines = [
            f"# 技术内容日报 - {now.strftime('%Y-%m-%d')}",
            "",
            f"> 生成时间：{now.isoformat()}  |  共 {len(items)} 条",
            "",
            "---",
            "",
        ]
        if not items:
            lines.extend(["## 无可用内容", "", "当前窗口内没有可生成日报的审核通过内容。", ""])
            return "\n".join(lines)

        for index, item in enumerate(items, start=1):
            title = str(item.get("title") or "Untitled")
            url = str(item.get("url") or "")
            source_type = str(item.get("source_type") or "")
            source_account = str(item.get("source_account") or "")
            category = str(item.get("category") or "")
            tags = item.get("tags") or []
            summary = str(item.get("summary") or "")
            lines.extend(
                [
                    f"## {index}. [{title}]({url})" if url else f"## {index}. {title}",
                    f"- **来源**：{source_type} / {source_account}",
                    f"- **分类**：{category}",
                    f"- **标签**：{', '.join(str(tag) for tag in tags)}",
                    f"- **摘要**：{summary}",
                    "",
                    "---",
                    "",
                ]
            )
        return "\n".join(lines)
