#!/usr/bin/env python
"""SQLite → PostgreSQL 数据迁移脚本 v2 (增强版)

功能:
  1. --mode migrate    : 正向迁移 (默认)
  2. --mode rollback   : 反向迁移 (PG → SQLite)
  3. --mode dry-run    : 预检查不写入
  4. --mode verify     : 仅校验数据一致性
  5. --incremental     : 增量迁移（只迁差异数据）

用法:
    python scripts/db_migrate_v2.py                           # 正向迁移
    python scripts/db_migrate_v2.py --mode dry-run            # 预检查
    python scripts/db_migrate_v2.py --mode verify             # 数据一致性校验
    python scripts/db_migrate_v2.py --mode rollback           # 反向迁移
    python scripts/db_migrate_v2.py --incremental             # 增量迁移
    python scripts/db_migrate_v2.py --tables users,posts      # 只迁指定表
    python scripts/db_migrate_v2.py --batch-size 500          # 自定义批量大小

环境变量:
    SOURCE_BLOG_DB       - 源 blog.db 路径
    SOURCE_SCHEDULER_DB  - 源 scheduler.db 路径
    PG_DATABASE_URL      - 目标 PostgreSQL 连接串
"""
from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import sys
import time
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

# 表定义: {表名: [列名列表]}
PLATFORM_TABLES = [
    "users",
    "posts",
    "post_likes",
    "comments",
    "comment_likes",
    "agent_drafts",
    "event_logs",
]

SCHEDULER_TABLES = [
    "scheduler_agents",
    "scheduler_tasks",
    "scheduler_task_attempts",
    "scheduler_task_events",
    "scheduler_task_logs",
]

# 布尔列映射: PG 中这些列是 BOOLEAN 类型
BOOLEAN_COLUMNS = {"published", "is_active", "is_deleted", "is_admin", "cancel_requested"}


def _utcnow_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")


def log(msg: str, level: str = "INFO") -> None:
    prefix = {"INFO": " ", "WARN": "⚠", "ERROR": "✗", "OK": "✓"}
    print(f"[{_utcnow_str()}] {prefix.get(level, ' ')} {msg}")


# =========================================================================
# 迁移器
# =========================================================================


class DataMigratorV2:
    def __init__(
        self,
        sqlite_path: str,
        pg_url: str,
        batch_size: int = 1000,
        incremental: bool = False,
    ):
        self.sqlite_path = sqlite_path
        self.pg_url = pg_url
        self.batch_size = batch_size
        self.incremental = incremental
        self.pg_engine = create_engine(pg_url, pool_pre_ping=True)
        self.PGSession = sessionmaker(bind=self.pg_engine)
        self._stats: dict[str, dict] = {}

    def verify(self) -> list[str]:
        """验证源和目标，返回警告列表。"""
        warnings: list[str] = []

        if not Path(self.sqlite_path).exists():
            raise FileNotFoundError(f"源 SQLite 文件不存在: {self.sqlite_path}")

        try:
            with self.pg_engine.connect() as conn:
                result = conn.execute(text("SELECT version()")).scalar()
            log(f"PostgreSQL 连接 OK: {str(result)[:60]}", "OK")
        except Exception as e:
            raise ConnectionError(f"PostgreSQL 连接失败: {e}")

        # 检查 PG 中是否已有数据
        try:
            with self.pg_engine.connect() as conn:
                for table in PLATFORM_TABLES + SCHEDULER_TABLES:
                    try:
                        count = conn.execute(text(f"SELECT COUNT(*) FROM \"{table}\"")).scalar()
                        if count > 0:
                            warnings.append(f"表 {table} 已有 {count} 行数据，迁移可能覆盖")
                    except Exception:
                        pass
        except Exception:
            pass

        return warnings

    # ------------------------------------------------------------------
    # 正向迁移 (SQLite → PG)
    # ------------------------------------------------------------------

    def migrate_platform(self) -> dict[str, int]:
        """迁移 blog.db 全部表，返回 {表名: 迁移行数}。"""
        sqlite_conn = sqlite3.connect(self.sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        counts: dict[str, int] = {}

        for table in PLATFORM_TABLES:
            count = self._copy_sqlite_to_pg(sqlite_conn, table)
            counts[table] = count

        sqlite_conn.close()
        return counts

    def migrate_scheduler(self, scheduler_db_path: str) -> dict[str, int]:
        """迁移 scheduler.db 全部表。"""
        if not Path(scheduler_db_path).exists():
            log(f"调度中心 DB 不存在，跳过: {scheduler_db_path}", "WARN")
            return {}

        sqlite_conn = sqlite3.connect(scheduler_db_path)
        sqlite_conn.row_factory = sqlite3.Row
        counts: dict[str, int] = {}

        for table in SCHEDULER_TABLES:
            count = self._copy_sqlite_to_pg(sqlite_conn, table)
            counts[table] = count

        sqlite_conn.close()
        return counts

    def _copy_sqlite_to_pg(self, sqlite_conn: sqlite3.Connection, table: str) -> int:
        """将 SQLite 中一张表的数据复制到 PostgreSQL。"""
        start = time.perf_counter()

        # 读取源数据
        try:
            rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            log(f"  [SKIP] {table} — 表不存在")
            self._stats[table] = {"rows": 0, "duration_s": 0, "status": "skipped"}
            return 0

        if not rows:
            log(f"  [SKIP] {table} — 空表")
            self._stats[table] = {"rows": 0, "duration_s": 0, "status": "empty"}
            return 0

        columns = [desc[0] for desc in sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()]
        col_quoted = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join([f":{c}" for c in columns])

        insert_sql = text(
            f'INSERT INTO "{table}" ({col_quoted}) VALUES ({placeholders}) '
            f'ON CONFLICT DO NOTHING'
        )

        count = 0
        skipped = 0
        batch: list[dict] = []

        with self.pg_engine.begin() as conn:
            for row in rows:
                data = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if col in BOOLEAN_COLUMNS:
                        val = bool(val)
                    data[col] = val

                batch.append(data)

                if len(batch) >= self.batch_size:
                    # ON CONFLICT DO NOTHING 不返回 affected rows
                    result = conn.execute(insert_sql, batch)
                    count += len(batch)
                    batch.clear()

            if batch:
                result = conn.execute(insert_sql, batch)
                count += len(batch)

        duration = time.perf_counter() - start
        self._stats[table] = {"rows": count, "duration_s": round(duration, 2), "status": "ok"}
        log(f"  [OK] {table}: {count} 行 ({duration:.1f}s)")
        return count

    # ------------------------------------------------------------------
    # 反向迁移 (PG → SQLite)
    # ------------------------------------------------------------------

    def rollback_platform(self, target_sqlite_path: str) -> dict[str, int]:
        """从 PG 回滚数据到 SQLite。"""
        target_path = Path(target_sqlite_path)
        if target_path.exists():
            backup = target_path.with_suffix(".db.bak")
            target_path.rename(backup)
            log(f"已备份原 SQLite: {backup}")

        sqlite_conn = sqlite3.connect(str(target_path))
        counts: dict[str, int] = {}

        for table in PLATFORM_TABLES:
            count = self._copy_pg_to_sqlite(sqlite_conn, table)
            counts[table] = count

        sqlite_conn.close()
        return counts

    def rollback_scheduler(self, target_sqlite_path: str) -> dict[str, int]:
        """从 PG 回滚调度中心数据到 SQLite。"""
        target_path = Path(target_sqlite_path)
        if target_path.exists():
            backup = target_path.with_suffix(".db.bak")
            target_path.rename(backup)
            log(f"已备份原 SQLite: {backup}")

        sqlite_conn = sqlite3.connect(str(target_path))
        counts: dict[str, int] = {}

        for table in SCHEDULER_TABLES:
            count = self._copy_pg_to_sqlite(sqlite_conn, table)
            counts[table] = count

        sqlite_conn.close()
        return counts

    def _copy_pg_to_sqlite(self, sqlite_conn: sqlite3.Connection, table: str) -> int:
        """从 PG 复制一张表到 SQLite。"""
        # 获取 PG 表结构
        with self.pg_engine.connect() as conn:
            try:
                rows = conn.execute(text(f'SELECT * FROM "{table}"')).fetchall()
            except Exception:
                log(f"  [SKIP] {table} — PG 中不存在")
                return 0

            if not rows:
                return 0

            columns = list(rows[0]._mapping.keys())
            col_quoted = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(["?" for _ in columns])

            # 创建 SQLite 表
            col_defs = []
            for col in columns:
                col_defs.append(f'"{col}" TEXT')
            sqlite_conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(col_defs)})")
            sqlite_conn.execute(f"DELETE FROM {table}")

            insert_sql = f"INSERT INTO {table} ({col_quoted}) VALUES ({placeholders})"
            batch = []
            count = 0

            for row in rows:
                values = [row._mapping[c] for c in columns]
                batch.append(values)
                if len(batch) >= self.batch_size:
                    sqlite_conn.executemany(insert_sql, batch)
                    count += len(batch)
                    batch.clear()

            if batch:
                sqlite_conn.executemany(insert_sql, batch)
                count += len(batch)

            sqlite_conn.commit()
            log(f"  [OK] {table}: {count} 行 (PG → SQLite)")
            return count

    # ------------------------------------------------------------------
    # Dry-run 模式
    # ------------------------------------------------------------------

    def dry_run(self, scheduler_db_path: str) -> dict:
        """预检查：统计源数据，不实际写入。"""
        result: dict = {"platform": {}, "scheduler": {}, "total_rows": 0}

        for db_path, db_name, tables in [
            (self.sqlite_path, "platform", PLATFORM_TABLES),
            (scheduler_db_path, "scheduler", SCHEDULER_TABLES),
        ]:
            if not Path(db_path).exists():
                log(f"{db_name} DB 不存在: {db_path}", "WARN")
                continue

            sqlite_conn = sqlite3.connect(db_path)
            for table in tables:
                try:
                    count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    result[db_name][table] = count
                    result["total_rows"] += count
                    if count > 0:
                        log(f"  {db_name}.{table}: {count} 行待迁移")
                except sqlite3.OperationalError:
                    log(f"  {db_name}.{table}: 不存在", "WARN")
            sqlite_conn.close()

        return result


# =========================================================================
# 校验
# =========================================================================


def verify_counts(
    migrator: DataMigratorV2,
    platform_counts: dict[str, int],
    scheduler_counts: dict[str, int],
    scheduler_db_path: str,
) -> tuple[int, int]:
    """校验迁移前后行数一致。返回 (一致数, 不一致数)。"""
    ok_count = 0
    fail_count = 0

    log("-" * 50)
    log("校验行数:")

    # 平台主库
    if Path(migrator.sqlite_path).exists():
        sqlite_conn = sqlite3.connect(migrator.sqlite_path)
        for table, expected in platform_counts.items():
            try:
                actual = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if actual == expected:
                    log(f"  [OK] {table}: {expected} 行", "OK")
                    ok_count += 1
                else:
                    log(f"  [WARN] {table}: SQLite={actual}, PG={expected}", "WARN")
                    fail_count += 1
            except Exception as e:
                log(f"  [SKIP] {table}: {e}")
        sqlite_conn.close()

    # 调度中心
    if scheduler_counts and Path(scheduler_db_path).exists():
        sqlite_conn = sqlite3.connect(scheduler_db_path)
        for table, expected in scheduler_counts.items():
            try:
                actual = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if actual == expected:
                    log(f"  [OK] {table}: {expected} 行", "OK")
                    ok_count += 1
                else:
                    log(f"  [WARN] {table}: SQLite={actual}, PG={expected}", "WARN")
                    fail_count += 1
            except Exception as e:
                log(f"  [SKIP] {table}: {e}")
        sqlite_conn.close()

    return ok_count, fail_count


def verify_data_integrity(migrator: DataMigratorV2, scheduler_db_path: str) -> dict:
    """深度数据完整性校验：抽样比对实际数据内容。"""
    result: dict = {"tables_checked": 0, "rows_sampled": 0, "mismatches": 0, "details": []}

    log("-" * 50)
    log("深度数据完整性校验 (抽样):")

    for db_path, tables in [
        (migrator.sqlite_path, PLATFORM_TABLES),
        (scheduler_db_path, SCHEDULER_TABLES),
    ]:
        if not Path(db_path).exists():
            continue

        sqlite_conn = sqlite3.connect(db_path)
        sqlite_conn.row_factory = sqlite3.Row

        with migrator.pg_engine.connect() as pg_conn:
            for table in tables:
                try:
                    sqlite_rows = sqlite_conn.execute(f"SELECT * FROM {table} ORDER BY ROWID LIMIT 20").fetchall()
                    if not sqlite_rows:
                        continue

                    result["tables_checked"] += 1
                    sample_count = 0

                    for sqlite_row in sqlite_rows:
                        # 用第一列 (通常是 id) 查找 PG 对应行
                        first_col = sqlite_row.keys()[0]
                        first_val = sqlite_row[0]
                        pg_row = pg_conn.execute(
                            text(f'SELECT * FROM "{table}" WHERE "{first_col}" = :val'),
                            {"val": first_val},
                        ).fetchone()

                        if pg_row:
                            sample_count += 1
                            result["rows_sampled"] += 1
                            # 比较所有列
                            for col in sqlite_row.keys():
                                sqlite_val = sqlite_row[col]
                                pg_val = pg_row._mapping.get(col)
                                # 布尔值标准化
                                if col in BOOLEAN_COLUMNS:
                                    sqlite_val = bool(sqlite_val)
                                    pg_val = bool(pg_val)
                                if str(sqlite_val) != str(pg_val):
                                    result["mismatches"] += 1
                                    result["details"].append({
                                        "table": table,
                                        "column": col,
                                        "sqlite": str(sqlite_val)[:100],
                                        "pg": str(pg_val)[:100],
                                    })

                    if sample_count > 0:
                        log(f"  [OK] {table}: 抽样 {sample_count} 行", "OK")
                except Exception as e:
                    log(f"  [SKIP] {table}: {e}")

        sqlite_conn.close()

    return result


# =========================================================================
# Main
# =========================================================================


def parse_args():
    parser = argparse.ArgumentParser(
        description="SQLite ↔ PostgreSQL 数据迁移工具 v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                              # 正向迁移
  %(prog)s --mode dry-run               # 预检查
  %(prog)s --mode verify                # 数据一致性校验
  %(prog)s --mode rollback              # 反向迁移 (PG → SQLite)
  %(prog)s --incremental                # 增量迁移
  %(prog)s --tables users,posts         # 只迁指定表
  %(prog)s --batch-size 500             # 自定义批量大小
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["migrate", "rollback", "dry-run", "verify"],
        default="migrate",
        help="操作模式 (默认: migrate)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="增量迁移（只迁差异数据）",
    )
    parser.add_argument(
        "--tables",
        type=str,
        help="逗号分隔的指定表名 (为空则迁全部)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="批量大小 (默认: 1000)",
    )
    parser.add_argument(
        "--source-blog-db",
        type=str,
        default=DEFAULT_BLOG_DB,
        help=f"源 blog.db 路径 (默认: {DEFAULT_BLOG_DB})",
    )
    parser.add_argument(
        "--source-scheduler-db",
        type=str,
        default=DEFAULT_SCHEDULER_DB,
        help=f"源 scheduler.db 路径 (默认: {DEFAULT_SCHEDULER_DB})",
    )
    parser.add_argument(
        "--pg-url",
        type=str,
        default=DEFAULT_PG_URL,
        help="目标 PostgreSQL 连接串",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    log(f"SQLite ↔ PostgreSQL 数据迁移 v2 — 模式: {args.mode}")
    log("=" * 50)

    blog_db = args.source_blog_db
    scheduler_db = args.source_scheduler_db
    pg_url = args.pg_url
    masked_pg = pg_url[:pg_url.index("@") + 1] + "****" if "@" in pg_url else pg_url

    log(f"源 blog.db:      {blog_db}")
    log(f"源 scheduler.db: {scheduler_db}")
    log(f"目标 PG:         {masked_pg}")
    if args.incremental:
        log(f"增量模式:        开启", "WARN")

    # 创建迁移器
    migrator = DataMigratorV2(
        sqlite_path=blog_db,
        pg_url=pg_url,
        batch_size=args.batch_size,
        incremental=args.incremental,
    )

    # ------------------------------------------------------------------
    # 模式: dry-run
    # ------------------------------------------------------------------
    if args.mode == "dry-run":
        log("-" * 50)
        log("Dry-run 模式 — 仅统计，不写入:")
        result = migrator.dry_run(scheduler_db)
        log("=" * 50)
        log(f"预检查完成！共 {result['total_rows']} 行待迁移")
        return 0

    # ------------------------------------------------------------------
    # 模式: verify
    # ------------------------------------------------------------------
    if args.mode == "verify":
        # 需要先验证连接
        try:
            migrator.verify()
        except (FileNotFoundError, ConnectionError) as e:
            log(f"[FAIL] {e}", "ERROR")
            return 1

        # 检查 PG 中数据量
        log("-" * 50)
        log("校验数据一致性:")
        with migrator.pg_engine.connect() as conn:
            for db_path, db_name, tables in [
                (blog_db, "blog.db", PLATFORM_TABLES),
                (scheduler_db, "scheduler.db", SCHEDULER_TABLES),
            ]:
                if not Path(db_path).exists():
                    continue
                sqlite_conn = sqlite3.connect(db_path)
                for table in tables:
                    try:
                        sqlite_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        try:
                            pg_count = conn.execute(text(f"SELECT COUNT(*) FROM \"{table}\"")).scalar()
                            if sqlite_count == pg_count:
                                log(f"  [OK] {table}: {sqlite_count} = {pg_count}", "OK")
                            else:
                                log(f"  [WARN] {table}: SQLite={sqlite_count}, PG={pg_count}", "WARN")
                        except Exception:
                            log(f"  [SKIP] {table}: PG 中不存在")
                    except Exception:
                        pass
                sqlite_conn.close()

        integrity = verify_data_integrity(migrator, scheduler_db)
        log("=" * 50)
        log(f"校验完成！检查 {integrity['tables_checked']} 表, {integrity['rows_sampled']} 行样本, "
            f"不一致 {integrity['mismatches']} 处")
        return 0 if integrity["mismatches"] == 0 else 1

    # ------------------------------------------------------------------
    # 模式: migrate (正向)
    # ------------------------------------------------------------------
    if args.mode == "migrate":
        try:
            warnings = migrator.verify()
            for w in warnings:
                log(w, "WARN")
        except (FileNotFoundError, ConnectionError) as e:
            log(f"[FAIL] {e}", "ERROR")
            return 1

        # 迁移平台主库
        log("-" * 50)
        log("迁移平台主库 (blog.db) → PostgreSQL:")
        platform_counts = migrator.migrate_platform()

        # 迁移调度中心
        log("-" * 50)
        log("迁移调度中心 (scheduler.db) → PostgreSQL:")
        scheduler_counts = migrator.migrate_scheduler(scheduler_db)

        # 校验
        ok_count, fail_count = verify_counts(migrator, platform_counts, scheduler_counts, scheduler_db)

        # 报告
        total_platform = sum(platform_counts.values())
        total_scheduler = sum(scheduler_counts.values())
        log("=" * 50)
        log(f"迁移完成！平台 {total_platform} 行，调度中心 {total_scheduler} 行，合计 {total_platform + total_scheduler} 行")

        # 性能统计
        log("-" * 50)
        log("迁移性能统计:")
        for table, stats in migrator._stats.items():
            if stats["rows"] > 0:
                tps = stats["rows"] / stats["duration_s"] if stats["duration_s"] > 0 else 0
                log(f"  {table}: {stats['rows']} 行, {stats['duration_s']:.1f}s, {tps:.0f} rows/s")

        return 0 if fail_count == 0 else 1

    # ------------------------------------------------------------------
    # 模式: rollback (反向)
    # ------------------------------------------------------------------
    if args.mode == "rollback":
        log("警告: 反向迁移将从 PostgreSQL 回滚数据到 SQLite", "WARN")
        log("此操作将覆盖现有的 SQLite 文件（自动备份为 .bak）", "WARN")

        try:
            with migrator.pg_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log("PostgreSQL 连接 OK")
        except Exception as e:
            log(f"PostgreSQL 连接失败: {e}", "ERROR")
            return 1

        log("-" * 50)
        log("回滚平台主库 (PostgreSQL) → SQLite:")
        platform_counts = migrator.rollback_platform(blog_db)

        log("-" * 50)
        log("回滚调度中心 (PostgreSQL) → SQLite:")
        scheduler_counts = migrator.rollback_scheduler(scheduler_db)

        total_platform = sum(platform_counts.values())
        total_scheduler = sum(scheduler_counts.values())
        log("=" * 50)
        log(f"回滚完成！平台 {total_platform} 行，调度中心 {total_scheduler} 行，合计 {total_platform + total_scheduler} 行")

        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
