from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import BackendUnavailable


@dataclass(frozen=True, slots=True)
class RedisConfig:
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "shared_mempool:"
    socket_timeout_seconds: float = 2.0
    socket_connect_timeout_seconds: float = 2.0


class RedisStore:
    def __init__(self, config: RedisConfig) -> None:
        try:
            import redis
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(str(exc)) from exc

        self._config = config
        self._client: Any = redis.Redis.from_url(
            config.url,
            socket_timeout=config.socket_timeout_seconds,
            socket_connect_timeout=config.socket_connect_timeout_seconds,
            decode_responses=False,
        )

    def close(self) -> None:
        pool = getattr(self._client, "connection_pool", None)
        if pool and hasattr(pool, "disconnect"):
            pool.disconnect()

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(str(exc)) from exc

    def get(self, key: str) -> bytes | None:
        try:
            value = self._client.get(self._config.key_prefix + key)
            return bytes(value) if value is not None else None
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(str(exc)) from exc

    def set(self, key: str, value: bytes, ttl_seconds: int | None) -> None:
        try:
            full_key = self._config.key_prefix + key
            if ttl_seconds is None:
                self._client.set(full_key, value)
            else:
                self._client.set(full_key, value, ex=int(ttl_seconds))
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(str(exc)) from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete(self._config.key_prefix + key)
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(str(exc)) from exc

    def ttl(self, key: str) -> int | None:
        try:
            value = self._client.ttl(self._config.key_prefix + key)
            if value is None or value < 0:
                return None
            return int(value)
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(str(exc)) from exc
