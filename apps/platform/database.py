"""
功能摘要：数据库连接引擎、连接池配置、会话管理、健康检查。

改动 (P2):
  - PostgreSQL 连接池配置 (pool_size, max_overflow, pool_pre_ping)
  - 新增 check_db_health() 健康检查函数
  - SQLite 分支保持不变
"""
from __future__ import annotations

import logging
import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

from apps.platform.core.config import settings

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = settings.resolved_database_url

# ---- 引擎配置 ----
_engine_kwargs: dict = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,  # 每小时回收连接
}

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL / MySQL 连接池分级配置
    # 通过 DB_POOL_TIER 环境变量控制:
    #   high   (Platform 主服务):   pool_size=20, max_overflow=40
    #   medium (Scheduler API):     pool_size=15, max_overflow=30
    #   low    (Dispatcher/Agent):  pool_size=5,  max_overflow=10
    _pool_tier = os.getenv("DB_POOL_TIER", "high")
    _pool_configs = {
        "high":   {"pool_size": 20, "max_overflow": 40, "pool_timeout": 30},
        "medium": {"pool_size": 15, "max_overflow": 30, "pool_timeout": 30},
        "low":    {"pool_size": 5,  "max_overflow": 10, "pool_timeout": 30},
    }
    _pool_cfg = _pool_configs.get(_pool_tier, _pool_configs["high"])
    _engine_kwargs.update({
        "pool_size": _pool_cfg["pool_size"],
        "max_overflow": _pool_cfg["max_overflow"],
        "pool_timeout": _pool_cfg["pool_timeout"],
        "echo_pool": False,
    })
    logger.info("DB pool tier=%s size=%d overflow=%d", _pool_tier, _pool_cfg["pool_size"], _pool_cfg["max_overflow"])

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)  # type: ignore[arg-type]

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 自定义基类：防止 import 双加载导致的 Table already defined 错误
from sqlalchemy import Table as _Table

_orig_table_new = _Table._new


def _patched_new(cls, *args, **kw):
    table_name = args[0] if args else "?"
    kw["extend_existing"] = True
    try:
        result = _orig_table_new(*args, **kw)
        if table_name == "posts":
            print(f"[DB_PATCH] posts: success, result={result}", flush=True)
        return result
    except Exception as e:
        if table_name == "posts":
            import traceback
            print(f"[DB_PATCH] posts: FAILED: {e}", flush=True)
            traceback.print_exc()
        raise


_Table._new = classmethod(_patched_new)
print("[DB_PATCH] Table._new patched with extend_existing=True", flush=True)

Base = declarative_base()


def get_db() -> Generator:
    """FastAPI 依赖注入：每次请求创建一个数据库会话，请求结束后自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> dict:
    """数据库健康检查。

    返回:
        {"status": "ok"} 或 {"status": "error", "detail": "..."}
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            # PostgreSQL 额外检查
            if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
                result = conn.execute(text("SELECT version()")).scalar()
                logger.debug("DB health check ok: %s", str(result)[:80])
        return {"status": "ok"}
    except OperationalError as e:
        logger.error("DB health check failed: %s", e)
        return {"status": "error", "detail": str(e)[:200]}
    except Exception as e:
        logger.exception("DB health check unexpected error")
        return {"status": "error", "detail": str(e)[:200]}
