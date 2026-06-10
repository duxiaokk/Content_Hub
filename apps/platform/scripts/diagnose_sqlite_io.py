#!/usr/bin/env python3
"""
SQLite disk I/O 诊断脚本

用法：
    .venv\Scripts\python.exe scripts\diagnose_sqlite_io.py [--path D:\\target_dir]

作用：
    1. 在目标目录创建测试数据库并建表
    2. 通过 SQLAlchemy 重复打开/写入/关闭，检测是否会出现 disk I/O error
    3. 模拟并发进程竞争写入（Windows 上常见的 journal 锁冲突场景）
    4. 输出诊断结论和建议
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


def _test_raw_sqlite(db_path: str) -> None:
    """原始 sqlite3 写入测试。"""
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("CREATE TABLE IF NOT EXISTS diag (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO diag (name) VALUES ('raw')")
    conn.commit()
    conn.close()


def _test_sqlalchemy(db_path: str) -> None:
    """SQLAlchemy 写入测试。"""
    from sqlalchemy import Column, Integer, String, create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker

    Base = declarative_base()

    class DiagTable(Base):
        __tablename__ = "diag_sa"
        id = Column(Integer, primary_key=True)
        name = Column(String(50))

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    sess.add(DiagTable(name="sqlalchemy"))
    sess.commit()
    sess.close()
    engine.dispose()


def _worker_write(db_path: str, worker_id: int) -> dict:
    """多进程 worker：各写入一条记录。"""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("INSERT INTO diag (name) VALUES (?)", (f"worker_{worker_id}",))
        conn.commit()
        conn.close()
        return {"ok": True, "worker": worker_id}
    except Exception as exc:
        return {"ok": False, "worker": worker_id, "error": str(exc)}


def run(target_dir: str | None = None) -> int:
    target = Path(target_dir) if target_dir else Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    test_db = target / "_diag_test.db"
    test_db_sa = target / "_diag_test_sa.db"

    print(f"诊断目录: {target.resolve()}")
    print(f"可用空间: {target.stat().st_dev}")  # 仅作标识
    print("-" * 50)

    # 1. 原始 sqlite3 测试
    try:
        if test_db.exists():
            os.remove(test_db)
        _test_raw_sqlite(str(test_db))
        print("[PASS] 原始 sqlite3 建表 + 写入")
        os.remove(test_db)
    except Exception as e:
        print(f"[FAIL] 原始 sqlite3 写入失败: {e}")
        return 1

    # 2. SQLAlchemy 测试
    try:
        if test_db_sa.exists():
            os.remove(test_db_sa)
        _test_sqlalchemy(str(test_db_sa))
        print("[PASS] SQLAlchemy create_all + 写入")
        os.remove(test_db_sa)
    except Exception as e:
        print(f"[FAIL] SQLAlchemy 写入失败: {e}")
        return 1

    # 3. 并发写入测试（模拟 journal 锁竞争）
    concurrent_db = target / "_diag_concurrent.db"
    if concurrent_db.exists():
        os.remove(concurrent_db)
    _test_raw_sqlite(str(concurrent_db))

    workers = 8
    print(f"[INFO] 启动 {workers} 个进程并发写入同一数据库...")
    with multiprocessing.Pool(workers) as pool:
        results = pool.starmap(_worker_write, [(str(concurrent_db), i) for i in range(workers)])

    failures = [r for r in results if not r["ok"]]
    if failures:
        print(f"[FAIL] 并发写入出现 {len(failures)} 次失败:")
        for f in failures[:3]:
            print(f"       worker {f['worker']}: {f['error']}")
    else:
        print(f"[PASS] 并发写入全部成功 ({workers}/{workers})")

    if concurrent_db.exists():
        os.remove(concurrent_db)

    # 4. 环境建议
    print("-" * 50)
    if failures:
        print("结论: 目标目录存在写入竞争或文件锁冲突。")
        print("建议:")
        print("  1. 换用 C 盘临时目录存放 SQLite 数据库（尤其是开发阶段）")
        print("  2. 避免 uvicorn --reload 与定时任务同时访问同一 db 文件")
        print("  3. 检查杀毒软件/受控文件夹访问是否拦截 Python 写入")
        return 1
    else:
        print("结论: 目标目录写入正常，未检测到 SQLite I/O 竞争。")
        print("若平台仍报错，请检查是否同时有多个进程/服务打开同一个 db 文件。")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SQLite I/O 诊断")
    parser.add_argument("--path", default=None, help="目标测试目录（默认当前目录）")
    args = parser.parse_args()
    sys.exit(run(args.path))
