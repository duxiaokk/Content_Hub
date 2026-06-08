"""Add platform semantic fields to posts table.

模块化改造：为 Post 模型新增 module_id, scenario_type, task_type 三个平台语义字段。
"""
from __future__ import annotations

import os
import sys

# 确保能找到项目根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from database import SessionLocal, engine


def migrate():
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("PRAGMA table_info(posts)"))
        columns = {row[1] for row in result.fetchall()}

        if "module_id" not in columns:
            conn.execute(text("ALTER TABLE posts ADD COLUMN module_id VARCHAR(64)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posts_module_id ON posts(module_id)"))
            print("[OK] Added posts.module_id")

        if "scenario_type" not in columns:
            conn.execute(text("ALTER TABLE posts ADD COLUMN scenario_type VARCHAR(64)"))
            print("[OK] Added posts.scenario_type")

        if "task_type" not in columns:
            conn.execute(text("ALTER TABLE posts ADD COLUMN task_type VARCHAR(128)"))
            print("[OK] Added posts.task_type")

        conn.commit()
        print("[DONE] Migration complete")


if __name__ == "__main__":
    migrate()
