from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ado_repost.processors.dedup import LinkDeduplicator, link_md5
from ado_repost.processors.formatter import MessageFormatter, StandardMessageFormatter
from ado_repost.processors.translator import PassthroughTranslator, Translator, contains_japanese
from ado_repost.schema import DynamicItem, HistoryRecord, ProcessBatch, ProcessedItem


class ContentProcessor:
    """读取 latest/history 数据，执行去重、翻译与格式化。"""

    def __init__(
        self,
        *,
        translator: Translator | None = None,
        formatter: MessageFormatter | None = None,
    ) -> None:
        self.translator = translator or PassthroughTranslator()
        self.formatter = formatter or StandardMessageFormatter()

    def process_paths(self, latest_path: str | Path, history_path: str | Path) -> ProcessBatch:
        latest_items = self._load_latest_items(Path(latest_path))
        history_records = self._load_history_records(Path(history_path))
        return self.process_items(latest_items, history_records)

    def process_items(
        self,
        latest_items: Iterable[DynamicItem],
        history_records: Iterable[HistoryRecord],
    ) -> ProcessBatch:
        latest_list = list(latest_items)
        history_list = list(history_records)
        deduplicator = LinkDeduplicator(history_list)
        fresh_items = deduplicator.filter_new_items(latest_list)

        processed_items = [self._process_one(item) for item in fresh_items]
        updated_history = history_list + deduplicator.build_history_records(fresh_items)

        return ProcessBatch(
            latest_items=latest_list,
            new_items=processed_items,
            updated_history=updated_history,
        )

    def _process_one(self, item: DynamicItem) -> ProcessedItem:
        translated_title = self._translate_if_needed(item.title, source_lang=item.language)
        translated_content = self._translate_if_needed(item.content, source_lang=item.language)
        processed = ProcessedItem(
            raw=item,
            dedup_key=link_md5(item.link),
            translated_title=translated_title,
            translated_content=translated_content,
            formatted_message="",
        )
        processed.formatted_message = self.formatter.format(processed)
        return processed

    def _translate_if_needed(self, text: str, *, source_lang: str | None = None) -> str:
        if not text.strip():
            return text

        normalized_lang = (source_lang or "").lower()
        should_translate = normalized_lang.startswith("ja") or contains_japanese(text)
        if not should_translate:
            return text
        return self.translator.translate(text, source_lang=source_lang, target_lang="zh-CN")

    def _load_latest_items(self, path: Path) -> list[DynamicItem]:
        payload = self._read_json(path, default=[])
        if isinstance(payload, dict):
            candidate = payload.get("items", [])
        else:
            candidate = payload
        if not isinstance(candidate, list):
            raise ValueError(f"latest 数据格式错误，期望 list，实际为 {type(candidate).__name__}")
        return [DynamicItem.from_dict(item) for item in candidate]

    def _load_history_records(self, path: Path) -> list[HistoryRecord]:
        payload = self._read_json(path, default=[])
        if isinstance(payload, dict):
            candidate = payload.get("items", payload.get("history", []))
        else:
            candidate = payload
        if not isinstance(candidate, list):
            raise ValueError(f"history 数据格式错误，期望 list，实际为 {type(candidate).__name__}")
        return [HistoryRecord.from_dict(item) for item in candidate]

    def _read_json(self, path: Path, *, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
