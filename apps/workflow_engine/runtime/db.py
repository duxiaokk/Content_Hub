from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _resolve_database_url() -> str:
    explicit_url = (os.getenv("DATABASE_URL") or "").strip()
    if explicit_url:
        return explicit_url
    sqlite_path = Path(__file__).resolve().parents[2] / "platform" / "blog.db"
    return f"sqlite:///{sqlite_path.as_posix()}"


DATABASE_URL = _resolve_database_url()

engine_kwargs: dict[str, object] = {
    "pool_pre_ping": True,
}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
