from __future__ import annotations

import abc
import json
import os
from typing import AsyncIterable

import httpx

from core.config import settings


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterable[str]:
        raise NotImplementedError


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 60,
    ):
        self.api_key = (api_key or settings.llm_api_key or "").strip()
        self.base_url = (base_url or settings.llm_base_url or "https://api.deepseek.com").rstrip("/")
        self.model = model or settings.llm_model or "deepseek-chat"
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else 0.7,
            "max_tokens": max_tokens if max_tokens is not None else 4096,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterable[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else 0.7,
            "max_tokens": max_tokens if max_tokens is not None else 4096,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line == "data: [DONE]":
                        break
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue


class MockProvider(LLMProvider):
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return (
            "【Mock 模式】\n"
            "这是模拟的 LLM 回复。请在 .env 中配置 LLM_API_KEY 和 LLM_BASE_URL，"
            "或将 MOCK_LLM 设为 true。"
        )

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterable[str]:
        text = await self.chat(system_prompt, user_prompt, temperature, max_tokens)
        for char in text:
            yield char


def get_default_provider() -> LLMProvider:
    raw_mock = (os.getenv("MOCK_LLM") or "").strip().lower()
    mock_from_env = raw_mock in {"1", "true", "yes", "on"}
    if settings.mock_llm or mock_from_env:
        return MockProvider()
    return OpenAICompatibleProvider()
