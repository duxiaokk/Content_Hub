from __future__ import annotations

import abc
import json
from typing import AsyncIterable

import httpx

from apps.ai_processor.runtime.settings import LLMSettings


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
    ) -> None:
        settings = LLMSettings()
        self.api_key = (api_key or settings.api_key).strip()
        self.base_url = (base_url or settings.base_url).rstrip("/")
        self.model = model or settings.model
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
            "temperature": 0.7 if temperature is None else temperature,
            "max_tokens": 4096 if max_tokens is None else max_tokens,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return str(data["choices"][0]["message"]["content"])

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
            "temperature": 0.7 if temperature is None else temperature,
            "max_tokens": 4096 if max_tokens is None else max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line == "data: [DONE]":
                        break
                    if not line.startswith("data: "):
                        continue
                    try:
                        chunk = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield str(delta)


class MockProvider(LLMProvider):
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return (
            "[Mock mode]\n"
            "This is a simulated LLM response. Configure LLM_API_KEY and LLM_BASE_URL, "
            "or set MOCK_LLM=true."
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
