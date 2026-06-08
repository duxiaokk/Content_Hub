from __future__ import annotations

from abc import ABC, abstractmethod

PROTECTED_TERMS = ("ライブ", "MV")


def contains_japanese(text: str) -> bool:
    return any(
        "\u3040" <= char <= "\u30ff" or "\u31f0" <= char <= "\u31ff"
        for char in text
    )


class Translator(ABC):
    """翻译接口抽象，统一处理术语保护。"""

    def translate(
        self,
        text: str,
        *,
        source_lang: str | None = None,
        target_lang: str = "zh-CN",
    ) -> str:
        if not text.strip():
            return text

        masked_text, placeholders = self._mask_protected_terms(text)
        translated = self._translate(masked_text, source_lang=source_lang, target_lang=target_lang)
        return self._restore_protected_terms(translated, placeholders)

    @abstractmethod
    def _translate(
        self,
        text: str,
        *,
        source_lang: str | None = None,
        target_lang: str = "zh-CN",
    ) -> str:
        """由具体实现对接翻译服务。"""

    def _mask_protected_terms(self, text: str) -> tuple[str, dict[str, str]]:
        masked_text = text
        placeholders: dict[str, str] = {}
        for index, term in enumerate(PROTECTED_TERMS):
            placeholder = f"__ADO_TERM_{index}__"
            if term in masked_text:
                masked_text = masked_text.replace(term, placeholder)
                placeholders[placeholder] = term
        return masked_text, placeholders

    def _restore_protected_terms(self, text: str, placeholders: dict[str, str]) -> str:
        restored = text
        for placeholder, term in placeholders.items():
            restored = restored.replace(placeholder, term)
        return restored


class PassthroughTranslator(Translator):
    """默认实现，不做实际翻译，方便后续注入第三方翻译能力。"""

    def _translate(
        self,
        text: str,
        *,
        source_lang: str | None = None,
        target_lang: str = "zh-CN",
    ) -> str:
        return text
