from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .errors import BackendUnavailable, LockTimeout, SharedMemoryError
from .redis_store import RedisConfig, RedisStore
from .sqlite_store import SqliteStore


@dataclass(frozen=True, slots=True)
class SharedMemoryConfig:
    namespace: str = "default"
    default_ttl_seconds: int | None = 3600
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "shared_memory:"
    redis_timeout_seconds: float = 2.0
    redis_connect_timeout_seconds: float = 2.0
    sqlite_path: str = "./shared_memory.db"
    sqlite_timeout_seconds: float = 2.0


def _now() -> int:
    return int(time.time())


def _build_namespace(namespace: str) -> str:
    ns = namespace.strip()
    return ns or "default"


def _build_compound_key(namespace: str, key: str) -> str:
    k = key.strip()
    if not k:
        raise ValueError("key is empty")
    return f"{_build_namespace(namespace)}:{k}"


def _dumps(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    except Exception as exc:
        raise SharedMemoryError(str(exc)) from exc


def _loads(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise SharedMemoryError(str(exc)) from exc


class SharedMemory:
    def __init__(self, config: SharedMemoryConfig | None = None) -> None:
        self._config = config or SharedMemoryConfig()
        sqlite_path = str(Path(self._config.sqlite_path))
        self._sqlite = SqliteStore(sqlite_path, timeout_seconds=self._config.sqlite_timeout_seconds)
        self._redis: RedisStore | None = None

    @property
    def sqlite_path(self) -> str:
        return self._sqlite.db_path

    @property
    def namespace(self) -> str:
        return _build_namespace(self._config.namespace)

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
            "namespace": self.namespace,
        }

    def get(
        self,
        key: str,
        *,
        namespace: str | None = None,
        timeout_seconds: float | None = None,
        default: Any | None = None,
    ) -> Any | None:
        ns = _build_namespace(namespace or self._config.namespace)
        compound = _build_compound_key(ns, key)

        redis_payload: bytes | None = None
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                redis_payload = self._redis.get(compound)
        except BackendUnavailable:
            redis_payload = None
        if redis_payload is not None:
            return _loads(redis_payload)

        record = self._sqlite.get(ns, key)
        if record is None:
            return default
        value = _loads(record.value)
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
        ns = _build_namespace(namespace or self._config.namespace)
        ttl = ttl_seconds if ttl_seconds is not None else self._config.default_ttl_seconds
        compound = _build_compound_key(ns, key)
        payload = _dumps(value)
        if persist:
            self._sqlite.put(ns, key, payload, ttl)
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                self._redis.set(compound, payload, ttl)
        except BackendUnavailable:
            pass

    def delete(self, key: str, *, namespace: str | None = None, timeout_seconds: float | None = None) -> None:
        ns = _build_namespace(namespace or self._config.namespace)
        compound = _build_compound_key(ns, key)
        self._sqlite.delete(ns, key)
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                self._redis.delete(compound)
        except BackendUnavailable:
            pass

    def purge_expired(self, namespace: str | None = None) -> int:
        ns = _build_namespace(namespace) if namespace else None
        return self._sqlite.purge_expired(namespace=ns)

    def export_jsonl(self, out_path: str | Path, namespace: str | None = None) -> dict[str, Any]:
        path = Path(out_path)
        ns = _build_namespace(namespace) if namespace else None
        exported = 0
        now = _now()
        with path.open("w", encoding="utf-8") as f:
            for r in self._sqlite.iter_records(ns):
                record = {
                    "namespace": r.namespace,
                    "key": r.key,
                    "updated_at": r.updated_at,
                    "expires_at": r.expires_at,
                    "now": now,
                    "payload_hex": r.value.hex(),
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
                    r_ns = _build_namespace(namespace)
                if not r_ns or not r_key:
                    skipped += 1
                    continue
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

    @contextmanager
    def lock(
        self,
        key: str,
        *,
        namespace: str | None = None,
        ttl_seconds: int = 30,
        timeout_seconds: float = 10.0,
        owner: str | None = None,
    ) -> Iterator[str]:
        ns = _build_namespace(namespace or self._config.namespace)
        compound = _build_compound_key(ns, key)
        lock_owner = owner or str(uuid4())
        used_redis = False
        try:
            self._ensure_redis(timeout_seconds=timeout_seconds)
            if self._redis is not None:
                self._redis.acquire_lock(
                    compound,
                    lock_owner,
                    ttl_seconds=int(ttl_seconds),
                    timeout_seconds=float(timeout_seconds),
                )
                used_redis = True
            else:
                self._sqlite.acquire_lock(
                    ns,
                    key,
                    lock_owner,
                    ttl_seconds=int(ttl_seconds),
                    timeout_seconds=float(timeout_seconds),
                )
        except TimeoutError as exc:
            raise LockTimeout(str(exc)) from exc
        except BackendUnavailable:
            try:
                self._sqlite.acquire_lock(
                    ns,
                    key,
                    lock_owner,
                    ttl_seconds=int(ttl_seconds),
                    timeout_seconds=float(timeout_seconds),
                )
            except TimeoutError as exc:
                raise LockTimeout(str(exc)) from exc
        try:
            yield lock_owner
        finally:
            try:
                if used_redis and self._redis is not None:
                    self._redis.release_lock(compound, lock_owner)
                else:
                    self._sqlite.release_lock(ns, key, lock_owner)
            except BackendUnavailable:
                self._sqlite.release_lock(ns, key, lock_owner)

    def _ensure_redis(self, timeout_seconds: float | None = None) -> None:
        if self._redis is not None:
            return
        cfg = RedisConfig(
            url=self._config.redis_url,
            key_prefix=self._config.redis_key_prefix,
            socket_timeout_seconds=float(timeout_seconds or self._config.redis_timeout_seconds),
            socket_connect_timeout_seconds=float(timeout_seconds or self._config.redis_connect_timeout_seconds),
        )
        try:
            self._redis = RedisStore(cfg)
        except BackendUnavailable:
            self._redis = None
        except Exception as exc:
            raise SharedMemoryError(str(exc)) from exc


MemoryPoolConfig = SharedMemoryConfig
MemoryPool = SharedMemory
