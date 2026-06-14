from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from apps.platform.scheduler_center.config import scheduler_settings

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = scheduler_settings.resolved_scheduler_database_url

# ---- 引擎配置 ----
_engine_kwargs: dict = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": float(scheduler_settings.scheduler_sqlite_busy_timeout_seconds),
    }
    _engine_kwargs.update({
        "pool_size": int(scheduler_settings.scheduler_db_pool_size),
        "max_overflow": int(scheduler_settings.scheduler_db_max_overflow),
        "pool_timeout": float(scheduler_settings.scheduler_db_pool_timeout_seconds),
    })
else:
    # PostgreSQL / MySQL 连接池配置
    _engine_kwargs.update({
        "pool_size": int(scheduler_settings.scheduler_db_pool_size),
        "max_overflow": int(scheduler_settings.scheduler_db_max_overflow),
        "pool_timeout": float(scheduler_settings.scheduler_db_pool_timeout_seconds),
    })

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)  # type: ignore[arg-type]

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()


def get_db() -> Generator:
    """FastAPI 依赖注入：每次请求创建独立会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> dict:
    """调度中心数据库健康检查。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except OperationalError as e:
        logger.error("Scheduler DB health check failed: %s", e)
        return {"status": "error", "detail": str(e)[:200]}
    except Exception as e:
        logger.exception("Scheduler DB health check unexpected error")
        return {"status": "error", "detail": str(e)[:200]}
