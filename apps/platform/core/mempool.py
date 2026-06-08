from __future__ import annotations

import os
import sys
from pathlib import Path

from core.config import BASE_DIR, settings

_workspace_shared_memory_src = Path(__file__).resolve().parents[3] / "libs" / "shared_memory" / "src"
_legacy_shared_memory_src = Path(__file__).resolve().parents[1] / "shared_memory" / "src"
for _candidate in (_workspace_shared_memory_src, _legacy_shared_memory_src):
    if _candidate.exists():
        sys.path.insert(0, str(_candidate))
        break

from shared_memory import MemoryPool, MemoryPoolConfig


def _env(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def _env_int(key: str, default: int) -> int:
    raw = _env(key)
    try:
        return int(raw) if raw is not None else int(default)
    except ValueError:
        return int(default)


_pool: MemoryPool | None = None


def get_pool() -> MemoryPool:
    global _pool
    if _pool is None:
        namespace = _env("SHARED_MEMORY_NAMESPACE") or "personal_blog"
        redis_url = _env("SHARED_MEMORY_REDIS_URL") or (
            settings.redis_url or "redis://localhost:6379/0"
        )
        redis_key_prefix = _env("SHARED_MEMORY_REDIS_KEY_PREFIX") or "shared_memory:"
        sqlite_path = _env("SHARED_MEMORY_SQLITE_PATH") or str(BASE_DIR / "shared_memory.db")
        default_ttl_seconds = _env_int("SHARED_MEMORY_DEFAULT_TTL_SECONDS", 3600)
        _pool = MemoryPool(
            MemoryPoolConfig(
                namespace=namespace,
                redis_url=redis_url,
                redis_key_prefix=redis_key_prefix,
                sqlite_path=sqlite_path,
                default_ttl_seconds=default_ttl_seconds,
            )
        )
    return _pool
