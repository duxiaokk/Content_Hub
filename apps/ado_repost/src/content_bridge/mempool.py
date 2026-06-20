from __future__ import annotations

import os
from pathlib import Path

from shared_memory import MemoryPool, MemoryPoolConfig


def create_pool() -> MemoryPool:
    data_dir = Path(__file__).parent.parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    default_sqlite = str(data_dir / "shared_memory.db")
    namespace = os.getenv("SHARED_MEMORY_NAMESPACE") or os.getenv("SHARED_MEMPOOL_NAMESPACE") or "ado-repost"
    redis_url = (
        os.getenv("SHARED_MEMORY_REDIS_URL") or os.getenv("SHARED_MEMPOOL_REDIS_URL") or "redis://localhost:6379/0"
    )
    redis_key_prefix = (
        os.getenv("SHARED_MEMORY_REDIS_KEY_PREFIX")
        or os.getenv("SHARED_MEMPOOL_REDIS_KEY_PREFIX")
        or "shared_memory:"
    )
    sqlite_path = os.getenv("SHARED_MEMORY_SQLITE_PATH") or os.getenv("SHARED_MEMPOOL_SQLITE_PATH") or default_sqlite
    return MemoryPool(
        MemoryPoolConfig(
            namespace=namespace,
            redis_url=redis_url,
            redis_key_prefix=redis_key_prefix,
            sqlite_path=sqlite_path,
        )
    )


pool = create_pool()
