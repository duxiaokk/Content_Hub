from __future__ import annotations

from abc import ABC, abstractmethod

from ado_repost.schema import ProcessedItem


class MessageFormatter(ABC):
    @abstractmethod
    def format(self, item: ProcessedItem) -> str:
        """将处理后的动态标准化为推送消息。"""


class StandardMessageFormatter(MessageFormatter):
    """统一的推送文案模板。"""

    def format(self, item: ProcessedItem) -> str:
        raw = item.raw
        header = self._build_header(item)
        body = item.translated_content or raw.content or "暂无正文"
        meta_parts = [
            f"来源：{raw.source or '未知来源'}",
            f"作者：{raw.author or 'Ado'}",
            f"时间：{raw.published_at or '未知时间'}",
        ]

        lines = [header, body]

        if raw.content and item.translated_content and item.translated_content != raw.content:
            lines.extend(["", f"原文：{raw.content}"])

        if raw.tags:
            lines.append(f"标签：{' / '.join(raw.tags)}")

        lines.extend(["", " | ".join(meta_parts), f"链接：{raw.link}"])
        return "\n".join(lines).strip()

    def _build_header(self, item: ProcessedItem) -> str:
        title = item.translated_title or item.raw.title
        if title:
            return f"【Ado 动态】{title}"
        return f"【Ado 动态】{item.raw.source or '动态更新'}"
