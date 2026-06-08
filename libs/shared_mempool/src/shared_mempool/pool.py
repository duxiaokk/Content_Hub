from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import BackendUnavailable, MemoryPoolError, SerializationError
from .redis_store import RedisConfig, RedisStore
from .serializers import Serializer, get_serializer
from .sqlite_store import SqliteStore


@dataclass(frozen=True, slots=True)
class MemoryPoolConfig:
    namespace: str = "default"
    default_ttl_seconds: int | None = 3600
    serializer: str = "json"
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "shared_mempool:"
    redis_timeout_seconds: float = 2.0
    redis_connect_timeout_seconds: float = 2.0
    sqlite_path: str = "./shared_mempool.db"


def _now() -> int:
    return int(time.time())


def _build_key(namespace: str, key: str) -> str:
    ns = namespace.strip()
    if not ns:
        ns = "default"
    k = key.strip()
    if not k:
        raise ValueError("key is empty")
    return f"{ns}:{k}"


def _encode_envelope(serializer: Serializer, value: Any) -> bytes:
    payload = serializer.dumps(value)
    envelope = {"s": serializer.name, "v": payload.decode("latin1")}
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _decode_envelope(payload: bytes) -> Any:
    try:
        envelope = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SerializationError(str(exc)) from exc
    if not isinstance(envelope, dict):
        raise SerializationError("invalid envelope")
    serializer_name = str(envelope.get("s") or "")
    raw = envelope.get("v")
    if not isinstance(raw, str):
        raise SerializationError("invalid envelope")
    serializer = get_serializer(serializer_name)
    return serializer.loads(raw.encode("latin1"))


class MemoryPool:
    def __init__(self, config: MemoryPoolConfig | None = None) -> None:
        self._config = config or MemoryPoolConfig()
        self._serializer: Serializer = get_serializer(self._config.serializer)
        sqlite_path = str(Path(self._config.sqlite_path))
        self._sqlite = SqliteStore(sqlite_path)
        self._redis: RedisStore | None = None

    @property
    def sqlite_path(self) -> str:
        return self._sqlite.db_path

    @property
    def namespace(self) -> str:
        return self._config.namespace

    def close(self) -> None:
        if self._redis is not None:
            self._redis.close()
        self._sqlite.close()

    def health(self, timeout_seconds: float | None = None) -> dict[str, Any]:
        redis_ok = False
        redis_error: str | None = None
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                redis_ok = self._redis.ping()
        except BackendUnavailable as exc:
            redis_error = str(exc)
        return {
            "redis_ok": redis_ok,
            "redis_error": redis_error,
            "sqlite_path": self._sqlite.db_path,
            "namespace": self._config.namespace,
            "serializer": self._serializer.name,
        }

    def get(self, key: str, *, namespace: str | None = None, timeout_seconds: float | None = None) -> Any | None:
        ns = namespace or self._config.namespace
        compound = _build_key(ns, key)
        redis_payload: bytes | None = None
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                redis_payload = self._redis.get(compound)
        except BackendUnavailable:
            redis_payload = None
        if redis_payload is not None:
            return _decode_envelope(redis_payload)

        record = self._sqlite.get(ns, key)
        if record is None:
            return None
        value = _decode_envelope(record.value)
        remaining_ttl: int | None
        if record.expires_at is None:
            remaining_ttl = None
        else:
            remaining_ttl = max(0, int(record.expires_at - _now()))
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                self._redis.set(compound, record.value, remaining_ttl)
        except BackendUnavailable:
            pass
        return value

    def set(
        self,
        key: str,
        value: Any,
        *,
        namespace: str | None = None,
        ttl_seconds: int | None = None,
        timeout_seconds: float | None = None,
        persist: bool = True,
    ) -> None:
        ns = namespace or self._config.namespace
        ttl = ttl_seconds if ttl_seconds is not None else self._config.default_ttl_seconds
        compound = _build_key(ns, key)
        envelope = _encode_envelope(self._serializer, value)
        if persist:
            self._sqlite.put(ns, key, envelope, ttl)
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                self._redis.set(compound, envelope, ttl)
        except BackendUnavailable:
            pass

    def delete(self, key: str, *, namespace: str | None = None, timeout_seconds: float | None = None) -> None:
        ns = namespace or self._config.namespace
        compound = _build_key(ns, key)
        self._sqlite.delete(ns, key)
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                self._redis.delete(compound)
        except BackendUnavailable:
            pass

    def purge_expired(self, namespace: str | None = None) -> int:
        return self._sqlite.purge_expired(namespace=namespace)

    def export_jsonl(self, out_path: str | Path, namespace: str | None = None) -> dict[str, Any]:
        path = Path(out_path)
        ns = namespace
        exported = 0
        now = _now()
        with path.open("w", encoding="utf-8") as f:
            for r_ns, r_key, r_value, r_updated_at, r_expires_at in self._sqlite.iter_records(ns):
                record = {
                    "namespace": r_ns,
                    "key": r_key,
                    "updated_at": r_updated_at,
                    "expires_at": r_expires_at,
                    "now": now,
                    "payload_hex": r_value.hex(),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                exported += 1
        return {"exported": exported, "path": str(path)}

    def import_jsonl(
        self,
        in_path: str | Path,
        *,
        namespace: str | None = None,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        path = Path(in_path)
        imported = 0
        skipped = 0
        now = _now()
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                record = json.loads(raw)
                r_ns = str(record.get("namespace") or "")
                r_key = str(record.get("key") or "")
                if namespace:
                    r_ns = namespace
                payload_hex = str(record.get("payload_hex") or "")
                expires_at = record.get("expires_at")
                if expires_at is not None:
                    expires_at = int(expires_at)
                if expires_at is not None and expires_at <= now:
                    skipped += 1
                    continue
                ttl_seconds: int | None
                if expires_at is None:
                    ttl_seconds = None
                else:
                    ttl_seconds = max(0, int(expires_at - now))
                existing = self._sqlite.get(r_ns, r_key)
                if existing is not None and not overwrite:
                    skipped += 1
                    continue
                payload = bytes.fromhex(payload_hex)
                self._sqlite.put(r_ns, r_key, payload, ttl_seconds)
                imported += 1
        return {"imported": imported, "skipped": skipped, "path": str(path)}

    def _ensure_redis(self, timeout_seconds: float | None = None) -> None:
        if self._redis is not None:
            return
        cfg = RedisConfig(
            url=self._config.redis_url,
            key_prefix=self._config.redis_key_prefix,
            socket_timeout_seconds=float(timeout_seconds or self._config.redis_timeout_seconds),
            socket_connect_timeout_seconds=float(
                timeout_seconds or self._config.redis_connect_timeout_seconds
            ),
        )
        try:
            self._redis = RedisStore(cfg)
        except BackendUnavailable:
            self._redis = None
        except Exception as exc:  # noqa: BLE001
            raise MemoryPoolError(str(exc)) from exc
