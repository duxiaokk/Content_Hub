from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class LLMSettings:
    api_key: str = (os.getenv("LLM_API_KEY") or "").strip()
    base_url: str = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model: str = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    mock_llm: bool = (os.getenv("MOCK_LLM") or "").strip().lower() in {"1", "true", "yes", "on"}
