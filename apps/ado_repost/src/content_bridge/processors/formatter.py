from __future__ import annotations

from abc import ABC, abstractmethod

from content_bridge.schema import ProcessedItem


class MessageFormatter(ABC):
    @abstractmethod
    def format(self, item: ProcessedItem) -> str:
        """灏嗗鐞嗗悗鐨勫姩鎬佹爣鍑嗗寲涓烘帹閫佹秷鎭€?""


class StandardMessageFormatter(MessageFormatter):
    """缁熶竴鐨勬帹閫佹枃妗堟ā鏉裤€?""

    def format(self, item: ProcessedItem) -> str:
        raw = item.raw
        header = self._build_header(item)
        body = item.translated_content or raw.content or "鏆傛棤姝ｆ枃"
        meta_parts = [
            f"鏉ユ簮锛歿raw.source or '鏈煡鏉ユ簮'}",
            f"浣滆€咃細{raw.author or 'Ado'}",
            f"鏃堕棿锛歿raw.published_at or '鏈煡鏃堕棿'}",
        ]

        lines = [header, body]

        if raw.content and item.translated_content and item.translated_content != raw.content:
            lines.extend(["", f"鍘熸枃锛歿raw.content}"])

        if raw.tags:
            lines.append(f"鏍囩锛歿' / '.join(raw.tags)}")

        lines.extend(["", " | ".join(meta_parts), f"閾炬帴锛歿raw.link}"])
        return "\n".join(lines).strip()

    def _build_header(self, item: ProcessedItem) -> str:
        title = item.translated_title or item.raw.title
        if title:
            return f"銆怉do 鍔ㄦ€併€憑title}"
        return f"銆怉do 鍔ㄦ€併€憑item.raw.source or '鍔ㄦ€佹洿鏂?}"

