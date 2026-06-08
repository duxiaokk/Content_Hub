from __future__ import annotations

import sys
from pathlib import Path

_shared_memory_src = Path(__file__).resolve().parents[4] / "libs" / "shared_memory" / "src"
if _shared_memory_src.exists():
    sys.path.insert(0, str(_shared_memory_src))

from shared_memory import MemoryPool, MemoryPoolConfig

from app.core.config import settings

pool = MemoryPool(
    MemoryPoolConfig(
        namespace=settings.mempool_namespace,
        redis_url=settings.mempool_redis_url,
        redis_key_prefix=settings.mempool_redis_key_prefix,
        sqlite_path=settings.mempool_sqlite_path,
        default_ttl_seconds=settings.mempool_default_ttl_seconds,
    )
)


def get_pool() -> MemoryPool:
    return pool
