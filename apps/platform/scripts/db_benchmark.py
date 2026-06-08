#!/usr/bin/env python
"""数据库性能压测脚本

使用 pgbench 风格对 PostgreSQL 进行读写压测。

用法:
    python scripts/db_benchmark.py                         # 默认混合压测
    python scripts/db_benchmark.py --mode read             # 纯读压测
    python scripts/db_benchmark.py --mode write            # 纯写压测
    python scripts/db_benchmark.py --concurrency 20 --duration 30  # 20并发30秒

目标:
    读取 TPS: > 1000
    写入 TPS: > 200
    p99 延迟: < 50ms
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

DEFAULT_PG_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("PG_DATABASE_URL", "postgresql://blog_user:blog_pass@localhost:5432/blog_db"),
)


@dataclass
class BenchmarkResult:
    """单次压测结果。"""
    mode: str = "mixed"
    concurrency: int = 0
    duration_seconds: float = 0.0
    total_ops: int = 0
    success_ops: int = 0
    fail_ops: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    tps: float = 0.0

    @property
    def p50_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.median(self.latencies_ms)

    @property
    def p95_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sorted(self.latencies_ms)[int(len(self.latencies_ms) * 0.95)]

    @property
    def p99_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sorted(self.latencies_ms)[int(len(self.latencies_ms) * 0.99)]

    @property
    def avg_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.mean(self.latencies_ms)

    @property
    def min_ms(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def success_rate(self) -> float:
        return self.success_ops / self.total_ops * 100 if self.total_ops > 0 else 0.0

    def report_dict(self) -> dict:
        return {
            "mode": self.mode,
            "concurrency": self.concurrency,
            "duration_s": round(self.duration_seconds, 1),
            "total_ops": self.total_ops,
            "success_ops": self.success_ops,
            "fail_ops": self.fail_ops,
            "success_rate": round(self.success_rate, 1),
            "tps": round(self.tps, 1),
            "latency_avg_ms": round(self.avg_ms, 1),
            "latency_min_ms": round(self.min_ms, 1),
            "latency_max_ms": round(self.max_ms, 1),
            "latency_p50_ms": round(self.p50_ms, 1),
            "latency_p95_ms": round(self.p95_ms, 1),
            "latency_p99_ms": round(self.p99_ms, 1),
        }


class DatabaseBenchmarker:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self._stop_event = threading.Event()
        self._results: list[tuple[str, float, bool]] = []
        self._lock = threading.Lock()

    def _create_engine(self):
        return create_engine(self.db_url, pool_size=5, max_overflow=10, pool_pre_ping=True)

    def _read_query(self, engine) -> tuple[str, float, bool]:
        """执行随机读查询。"""
        queries = [
            "SELECT * FROM posts ORDER BY created_at DESC LIMIT 20",
            "SELECT COUNT(*) FROM posts",
            "SELECT * FROM users WHERE id = 1",
            "SELECT * FROM comments WHERE post_id = (SELECT id FROM posts ORDER BY RANDOM() LIMIT 1) LIMIT 10",
            "SELECT p.*, u.username FROM posts p JOIN users u ON p.user_id = u.id ORDER BY p.created_at DESC LIMIT 10",
        ]
        query = random.choice(queries)
        start = time.perf_counter()
        try:
            with engine.connect() as conn:
                conn.execute(text(query))
            return query[:50], (time.perf_counter() - start) * 1000, True
        except Exception as e:
            return query[:50], (time.perf_counter() - start) * 1000, False

    def _write_query(self, engine) -> tuple[str, float, bool]:
        """执行写操作（事务内完成+回滚避免污染数据）。"""
        test_id = str(uuid.uuid4())[:8]
        queries_with_rollback = [
            # 插入测试事件日志 (回滚)
            f"""
            BEGIN;
            INSERT INTO event_logs (id, event_type, description, created_at)
            VALUES ('{test_id}', 'benchmark', 'Benchmark test event', NOW());
            ROLLBACK;
            """,
        ]
        query = random.choice(queries_with_rollback)
        start = time.perf_counter()
        try:
            with engine.connect() as conn:
                # 分句执行
                for stmt in query.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(text(stmt))
                conn.commit()
            return "write_benchmark", (time.perf_counter() - start) * 1000, True
        except Exception as e:
            return "write_benchmark", (time.perf_counter() - start) * 1000, False

    def _mixed_query(self, engine) -> tuple[str, float, bool]:
        """混合读写。"""
        if random.random() < 0.7:  # 70% 读
            return self._read_query(engine)
        else:
            return self._write_query(engine)

    def _worker(self, mode: str, engine):
        """单 worker 循环。"""
        while not self._stop_event.is_set():
            if mode == "read":
                result = self._read_query(engine)
            elif mode == "write":
                result = self._write_query(engine)
            else:
                result = self._mixed_query(engine)
            with self._lock:
                self._results.append(result)

    def run(self, mode: str = "mixed", concurrency: int = 10, duration: int = 30):
        """执行压测。"""
        print(f"\n{'='*60}")
        print(f"  数据库压测: mode={mode}, concurrency={concurrency}, duration={duration}s")
        print(f"{'='*60}\n")

        self._results = []
        self._stop_event.clear()

        engines = [self._create_engine() for _ in range(concurrency)]
        threads = []

        start_time = time.perf_counter()

        # 启动 worker 线程
        for i in range(concurrency):
            t = threading.Thread(
                target=self._worker,
                args=(mode, engines[i]),
                daemon=True,
            )
            t.start()
            threads.append(t)

        # 等待
        self._stop_event.wait(timeout=duration)
        self._stop_event.set()

        # 等待线程结束
        for t in threads:
            t.join(timeout=3)

        elapsed = time.perf_counter() - start_time

        # 清理引擎
        for e in engines:
            try:
                e.dispose()
            except Exception:
                pass

        # 构建结果
        result = BenchmarkResult(
            mode=mode,
            concurrency=concurrency,
            duration_seconds=elapsed,
            total_ops=len(self._results),
            success_ops=sum(1 for _, _, ok in self._results if ok),
            fail_ops=sum(1 for _, _, ok in self._results if not ok),
            latencies_ms=[lat for _, lat, _ in self._results],
            tps=len(self._results) / elapsed if elapsed > 0 else 0,
        )
        return result


def print_report(result: BenchmarkResult):
    """打印压测报告。"""
    print(f"\n{'='*60}")
    print(f"  压测报告")
    print(f"{'='*60}")
    print(f"  模式:         {result.mode}")
    print(f"  并发:         {result.concurrency}")
    print(f"  持续时间:     {result.duration_seconds:.1f}s")
    print(f"{'─'*60}")
    print(f"  总操作数:     {result.total_ops}")
    print(f"  成功:         {result.success_ops} ({result.success_rate:.1f}%)")
    print(f"  失败:         {result.fail_ops}")
    print(f"  TPS:          {result.tps:.1f}")
    print(f"{'─'*60}")
    print(f"  延迟 (ms):")
    print(f"    avg:        {result.avg_ms:.1f}")
    print(f"    min:        {result.min_ms:.1f}")
    print(f"    max:        {result.max_ms:.1f}")
    print(f"    p50:        {result.p50_ms:.1f}")
    print(f"    p95:        {result.p95_ms:.1f}")
    print(f"    p99:        {result.p99_ms:.1f}")
    print(f"{'='*60}\n")

    # 验收判定
    checks = []
    if result.mode in ("read", "mixed") and result.tps < 1000:
        checks.append(f"  ✗ 读取 TPS {result.tps:.1f} < 目标 1000")
    else:
        checks.append(f"  ✓ 读取 TPS {result.tps:.1f}")
    if result.mode in ("write", "mixed") and result.tps < 200:
        checks.append(f"  ✗ 写入 TPS {result.tps:.1f} < 目标 200")
    if result.p99_ms > 50:
        checks.append(f"  ✗ p99 延迟 {result.p99_ms:.1f}ms > 目标 50ms")
    else:
        checks.append(f"  ✓ p99 延迟 {result.p99_ms:.1f}ms")
    if result.success_rate < 99:
        checks.append(f"  ✗ 成功率 {result.success_rate:.1f}% < 目标 99%")
    else:
        checks.append(f"  ✓ 成功率 {result.success_rate:.1f}%")

    print("验收判定:")
    for c in checks:
        print(c)
    print()


def main():
    parser = argparse.ArgumentParser(description="数据库性能压测")
    parser.add_argument("--mode", choices=["read", "write", "mixed"], default="mixed", help="压测模式")
    parser.add_argument("--concurrency", "-c", type=int, default=10, help="并发数")
    parser.add_argument("--duration", "-d", type=int, default=30, help="持续时间(秒)")
    parser.add_argument("--db-url", type=str, default=DEFAULT_PG_URL, help="PostgreSQL 连接串")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--suite", action="store_true", help="运行完整压测套件 (read/write/mixed)")
    args = parser.parse_args()

    db_url = args.db_url
    if "****" in db_url:
        db_url = os.getenv("DATABASE_URL", DEFAULT_PG_URL)

    # 连接检查
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            print(f"✓ PostgreSQL: {str(version)[:60]}")
        engine.dispose()
    except Exception as e:
        print(f"✗ PostgreSQL 连接失败: {e}")
        return 1

    benchmarker = DatabaseBenchmarker(db_url)

    if args.suite:
        # 完整套件
        results = {}
        configs = [
            ("read", 5, 15),
            ("read", 20, 15),
            ("write", 5, 15),
            ("write", 10, 15),
            ("mixed", 10, 30),
            ("mixed", 20, 30),
        ]
        for mode, conc, dur in configs:
            r = benchmarker.run(mode=mode, concurrency=conc, duration=dur)
            results[f"{mode}_c{conc}"] = r.report_dict()
            print_report(r)

        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        result = benchmarker.run(
            mode=args.mode,
            concurrency=args.concurrency,
            duration=args.duration,
        )
        print_report(result)

        if args.json:
            print(json.dumps(result.report_dict(), indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
