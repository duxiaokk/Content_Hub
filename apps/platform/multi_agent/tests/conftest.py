from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 将项目根目录和 platform 目录加入 sys.path，确保 apps.* 和 scheduler_center 等模块可被导入
REPO_ROOT = Path(__file__).resolve().parents[4]  # apps/platform/multi_agent/tests -> project root
PLATFORM_DIR = REPO_ROOT / "apps" / "platform"

for path in (str(REPO_ROOT), str(PLATFORM_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

# 设置最小环境变量，避免配置模块在导入时抛错
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-content-hub-jwt-32bytes-min")


# 导入 scheduler_center 的 Base，用于创建测试数据库
from scheduler_center.database import Base  # noqa: E402
from scheduler_center import models  # noqa: E402, F401 — 确保表注册到 Base.metadata

import pytest  # noqa: E402


@pytest.fixture
def db_session(tmp_path):
    """为测试提供独立的 SQLite Session，自动创建所有 scheduler_center 表。"""
    db_path = tmp_path / "test_scheduler.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
