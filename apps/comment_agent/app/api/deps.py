from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.mempool import get_pool
from shared_memory import MemoryPool


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_mempool() -> MemoryPool:
    return get_pool()
