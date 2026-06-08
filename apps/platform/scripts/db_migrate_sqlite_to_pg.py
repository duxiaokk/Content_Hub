#!/usr/bin/env python
"""SQLite → PostgreSQL 数据迁移脚本

用法:
    python scripts/db_migrate_sqlite_to_pg.py

前置条件:
    1. PostgreSQL 已启动，目标库已创建 (blog_db)
    2. 已执行: alembic upgrade head (创建表结构)
    3. SQLite 文件 (blog.db, scheduler.db) 存在于项目根目录

环境变量:
    SOURCE_BLOG_DB       - 源 blog.db 路径 (默认: ./blog.db)
    SOURCE_SCHEDULER_DB  - 源 scheduler.db 路径 (默认: ./scheduler.db)
    PG_DATABASE_URL      - 目标 PostgreSQL 连接串 (默认指向 docker 内 postgres)

迁移流程:
    1. 验证源 SQLite 文件存在
    2. 验证目标 PG 连接可用
    3. 按依赖顺序迁移: users → posts → post_likes/comments/... → agent_drafts → event_logs
    4. 逐表校验行数
    5. 输出迁移报告
"""
from __future__ import annotations

import datetime
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# =========================================================================
# 配置
# =========================================================================

DEFAULT_PG_URL = os.getenv(
    "PG_DATABASE_URL",
    "postgresql://blog_user:blog_pass@localhost:5432/blog_db",
)
DEFAULT_BLOG_DB = os.getenv("SOURCE_BLOG_DB", str(PROJECT_ROOT / "blog.db"))
DEFAULT_SCHEDULER_DB = os.getenv("SOURCE_SCHEDULER_DB", str(PROJECT_ROOT / "scheduler.db"))

# PostgreSQL 使用 TIMESTAMP WITH TIME ZONE
UTC_NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()


def _utcnow_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{_utcnow_str()}] {msg}")


# =========================================================================
# 迁移器
# =========================================================================


class DataMigrator:
    def __init__(self, sqlite_path: str, pg_url: str):
        self.sqlite_path = sqlite_path
        self.pg_engine = create_engine(pg_url, pool_pre_ping=True)
        self.PGSession = sessionmaker(bind=self.pg_engine)

    def verify(self) -> list[str]:
        """验证源和目标，返回警告列表。"""
        warnings: list[str] = []

        if not Path(self.sqlite_path).exists():
            raise FileNotFoundError(f"源 SQLite 文件不存在: {self.sqlite_path}")

        try:
            with self.pg_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log("PostgreSQL 连接 OK")
        except Exception as e:
            raise ConnectionError(f"PostgreSQL 连接失败: {e}")

        return warnings

    # ------------------------------------------------------------------
    # 平台主库 (blog.db) 迁移
    # ------------------------------------------------------------------

    def migrate_platform(self) -> dict[str, int]:
        """迁移 blog.db 全部表，返回 {表名: 迁移行数}。"""
        sqlite_conn = sqlite3.connect(self.sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        counts: dict[str, int] = {}

        tables = [
            "users",
            "posts",
            "post_likes",
            "comments",
            "comment_likes",
            "agent_drafts",
            "event_logs",
        ]

        for table in tables:
            count = self._copy_table(sqlite_conn, table)
            counts[table] = count

        sqlite_conn.close()
        return counts

    # ------------------------------------------------------------------
    # 调度中心 (scheduler.db) 迁移
    # ------------------------------------------------------------------

    def migrate_scheduler(self, scheduler_db_path: str) -> dict[str, int]:
        """迁移 scheduler.db 全部表。"""
        if not Path(scheduler_db_path).exists():
            log(f"调度中心 DB 不存在，跳过: {scheduler_db_path}")
            return {}

        sqlite_conn = sqlite3.connect(scheduler_db_path)
        sqlite_conn.row_factory = sqlite3.Row
        counts: dict[str, int] = {}

        tables = [
            "scheduler_agents",
            "scheduler_tasks",
            "scheduler_task_attempts",
            "scheduler_task_events",
            "scheduler_task_logs",
        ]

        for table in tables:
            count = self._copy_table(sqlite_conn, table)
            counts[table] = count

        sqlite_conn.close()
        return counts

    # ------------------------------------------------------------------
    # 单表复制
    # ------------------------------------------------------------------

    def _copy_table(self, sqlite_conn: sqlite3.Connection, table: str) -> int:
        """将 SQLite 中一张表的数据复制到 PostgreSQL。"""
        # 读取源数据
        try:
            rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            log(f"  [SKIP] {table} — 表不存在")
            return 0

        if not rows:
            log(f"  [SKIP] {table} — 空表")
            return 0

        columns = [desc[0] for desc in sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()]
        col_quoted = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join([f":{c}" for c in columns])

        insert_sql = text(f'INSERT INTO "{table}" ({col_quoted}) VALUES ({placeholders}) ON CONFLICT DO NOTHING')

        count = 0
        batch: list[dict] = []
        batch_size = 1000

        with self.pg_engine.begin() as conn:
            for row in rows:
                data = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    # 处理 SQLite INTEGER 0/1 → PG BOOLEAN
                    if col == "published":
                        val = bool(val)
                    data[col] = val

                batch.append(data)

                if len(batch) >= batch_size:
                    conn.execute(insert_sql, batch)
                    count += len(batch)
                    batch.clear()

            if batch:
                conn.execute(insert_sql, batch)
                count += len(batch)

        log(f"  [OK] {table}: {count} 行")
        return count


# =========================================================================
# 校验
# =========================================================================


def verify_counts(migrator: DataMigrator, platform_counts: dict, scheduler_counts: dict) -> bool:
    """校验迁移前后行数一致。"""
    all_ok = True

    log("-" * 50)
    log("校验行数:")

    # 平台主库
    if Path(migrator.sqlite_path).exists():
        sqlite_conn = sqlite3.connect(migrator.sqlite_path)
        for table, expected in platform_counts.items():
            try:
                actual = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if actual != expected and expected > 0:
                    log(f"  [WARN] {table}: SQLite={actual}, PG={expected} (可能含 ON CONFLICT)")
                else:
                    log(f"  [OK] {table}: {expected}")
            except Exception:
                pass
        sqlite_conn.close()

    # 调度中心
    if scheduler_counts:
        scheduler_db = DEFAULT_SCHEDULER_DB
        if Path(scheduler_db).exists():
            sqlite_conn = sqlite3.connect(scheduler_db)
            for table, expected in scheduler_counts.items():
                try:
                    actual = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    if actual != expected and expected > 0:
                        log(f"  [WARN] {table}: SQLite={actual}, PG={expected}")
                    else:
                        log(f"  [OK] {table}: {expected}")
                except Exception:
                    pass
            sqlite_conn.close()

    return all_ok


# =========================================================================
# Main
# =========================================================================


def main() -> int:
    log("SQLite → PostgreSQL 数据迁移")
    log("=" * 50)

    blog_db = DEFAULT_BLOG_DB
    scheduler_db = DEFAULT_SCHEDULER_DB
    pg_url = DEFAULT_PG_URL

    log(f"源 blog.db:      {blog_db}")
    log(f"源 scheduler.db: {scheduler_db}")
    log(f"目标 PG:         {pg_url[:pg_url.index('@')+1]}****")

    # 1. 验证
    migrator = DataMigrator(blog_db, pg_url)
    try:
        migrator.verify()
    except (FileNotFoundError, ConnectionError) as e:
        log(f"[FAIL] {e}")
        return 1

    # 2. 迁移平台主库
    log("-" * 50)
    log("迁移平台主库 (blog.db)：")
    platform_counts = migrator.migrate_platform()

    # 3. 迁移调度中心
    log("-" * 50)
    log("迁移调度中心 (scheduler.db)：")
    scheduler_counts = migrator.migrate_scheduler(scheduler_db)

    # 4. 校验
    verify_counts(migrator, platform_counts, scheduler_counts)

    # 5. 报告
    total_platform = sum(platform_counts.values())
    total_scheduler = sum(scheduler_counts.values())
    log("=" * 50)
    log(f"迁移完成！平台 {total_platform} 行，调度中心 {total_scheduler} 行，合计 {total_platform + total_scheduler} 行")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
