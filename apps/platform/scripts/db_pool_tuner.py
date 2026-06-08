#!/usr/bin/env python
"""数据库连接池自动调优工具

分析当前连接使用情况，给出连接池优化建议。

用法:
    python scripts/db_pool_tuner.py                    # 分析并输出建议
    python scripts/db_pool_tuner.py --apply            # 自动应用建议到配置文件
    python scripts/db_pool_tuner.py --check            # 仅检查当前状态
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text

# =========================================================================
# 默认配置
# =========================================================================

DEFAULT_PG_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("PG_DATABASE_URL", "postgresql://blog_user:blog_pass@localhost:5432/blog_db"),
)

# 连接池推荐策略
# 公式: pool_size = max_connections / num_services
# max_overflow = pool_size * 2 (突发缓冲)
TUNING_RECOMMENDATIONS = {
    # 服务名: (pool_size, max_overflow, pool_timeout, 说明)
    "platform": (20, 40, 30, "高并发 Web 请求"),
    "scheduler-api": (15, 30, 30, "中并发 API"),
    "scheduler-dispatcher": (5, 10, 60, "低并发轮询"),
    "scheduler-ingest": (3, 5, 60, "低并发摄入"),
    "agent": (5, 10, 30, "低并发单任务"),
}


def get_pg_settings(db_url: str) -> dict:
    """获取 PostgreSQL 关键配置。"""
    engine = create_engine(db_url, pool_pre_ping=True)
    settings = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT name, setting, unit, context
                FROM pg_settings
                WHERE name IN (
                    'max_connections',
                    'shared_buffers',
                    'effective_cache_size',
                    'work_mem',
                    'maintenance_work_mem',
                    'wal_buffers',
                    'checkpoint_timeout'
                )
            """)).fetchall()
            for row in rows:
                settings[row.name] = {
                    "value": row.setting,
                    "unit": row.unit or "",
                    "context": row.context,
                }
    except Exception as e:
        print(f"获取 PG 配置失败: {e}")
    finally:
        engine.dispose()
    return settings


def get_pool_stats(db_url: str) -> dict:
    """获取当前连接池状态。"""
    engine = create_engine(db_url, pool_pre_ping=True)
    stats = {
        "total_connections": 0,
        "active_connections": 0,
        "idle_connections": 0,
        "waiting_connections": 0,
        "max_connections": 100,
        "usage_percent": 0.0,
        "queries": [],
    }
    try:
        with engine.connect() as conn:
            # 连接数统计
            result = conn.execute(text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE state = 'active') AS active,
                    COUNT(*) FILTER (WHERE state = 'idle') AS idle,
                    COUNT(*) FILTER (WHERE wait_event IS NOT NULL) AS waiting,
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_conn
                FROM pg_stat_activity
                WHERE datname = current_database()
            """)).fetchone()

            if result:
                stats["total_connections"] = result.total
                stats["active_connections"] = result.active
                stats["idle_connections"] = result.idle
                stats["waiting_connections"] = result.waiting
                stats["max_connections"] = result.max_conn
                stats["usage_percent"] = round(result.total / result.max_conn * 100, 1) if result.max_conn else 0

            # 慢查询 Top 5
            slow_queries = conn.execute(text("""
                SELECT
                    query,
                    calls,
                    round(mean_exec_time::numeric, 2) AS avg_ms,
                    round(total_exec_time::numeric, 2) AS total_ms
                FROM pg_stat_statements
                WHERE query NOT LIKE '%pg_stat%'
                ORDER BY mean_exec_time DESC
                LIMIT 5
            """)).fetchall()

            for q in slow_queries:
                stats["queries"].append({
                    "query": str(q.query)[:120],
                    "calls": q.calls,
                    "avg_ms": float(q.avg_ms),
                    "total_ms": float(q.total_ms),
                })
    except Exception as e:
        print(f"获取连接池状态失败: {e}")
    finally:
        engine.dispose()
    return stats


def analyze_and_recommend(pg_settings: dict, pool_stats: dict) -> list[dict]:
    """分析当前状态并给出建议。"""
    recommendations: list[dict] = []

    # 1. 连接使用率
    usage = pool_stats.get("usage_percent", 0)
    if usage > 80:
        recommendations.append({
            "severity": "HIGH",
            "category": "连接数",
            "issue": f"连接使用率 {usage}% (接近上限)",
            "recommendation": f"考虑增加 max_connections 或减少服务连接池。当前 {pool_stats.get('total_connections')}/{pool_stats.get('max_connections')}",
        })
    elif usage > 60:
        recommendations.append({
            "severity": "MEDIUM",
            "category": "连接数",
            "issue": f"连接使用率 {usage}%，需关注趋势",
            "recommendation": "建议监控连接数增长，必要时调整 pool_size",
        })

    # 2. 等待连接
    waiting = pool_stats.get("waiting_connections", 0)
    if waiting > 0:
        recommendations.append({
            "severity": "HIGH",
            "category": "连接等待",
            "issue": f"有 {waiting} 个连接在等待 (连接池耗尽)",
            "recommendation": "增加 pool_size 或 max_overflow，检查是否有连接泄漏",
        })

    # 3. shared_buffers 建议
    sb = pg_settings.get("shared_buffers", {}).get("value", "0")
    try:
        sb_mb = int(sb.replace("kB", "")) // 8 if "kB" in sb else int(sb) if sb.isdigit() else 0
        if sb_mb < 256:
            recommendations.append({
                "severity": "MEDIUM",
                "category": "内存配置",
                "issue": f"shared_buffers = {sb}，建议至少 256MB",
                "recommendation": "在 postgresql.conf 中设置 shared_buffers = 256MB (内存的 25%)",
            })
    except (ValueError, AttributeError):
        pass

    # 4. 慢查询分析
    slow_queries = pool_stats.get("queries", [])
    if slow_queries:
        avg_ms = slow_queries[0].get("avg_ms", 0)
        if avg_ms > 100:
            recommendations.append({
                "severity": "MEDIUM",
                "category": "查询性能",
                "issue": f"慢查询: avg={avg_ms}ms, query={slow_queries[0].get('query', '')[:80]}",
                "recommendation": "建议添加索引或优化查询",
            })

    return recommendations


def print_report(pg_settings: dict, pool_stats: dict, recommendations: list[dict]):
    """打印完整报告。"""
    print()
    print("=" * 60)
    print("  数据库连接池诊断报告")
    print("=" * 60)
    print()

    # PG 配置
    print("── PostgreSQL 关键配置 ──")
    for name, info in pg_settings.items():
        unit = f" {info['unit']}" if info['unit'] else ""
        print(f"  {name:25s} = {info['value']}{unit}")
    print()

    # 连接池状态
    print("── 连接池状态 ──")
    print(f"  总连接数:     {pool_stats.get('total_connections', 'N/A')}")
    print(f"  活跃连接:     {pool_stats.get('active_connections', 'N/A')}")
    print(f"  空闲连接:     {pool_stats.get('idle_connections', 'N/A')}")
    print(f"  等待连接:     {pool_stats.get('waiting_connections', 'N/A')}")
    print(f"  最大连接:     {pool_stats.get('max_connections', 'N/A')}")
    print(f"  使用率:       {pool_stats.get('usage_percent', 0)}%")
    print()

    # 慢查询
    if pool_stats.get("queries"):
        print("── 慢查询 Top 5 ──")
        for i, q in enumerate(pool_stats["queries"], 1):
            print(f"  {i}. avg={q['avg_ms']}ms, calls={q['calls']}")
            print(f"     {q['query'][:100]}")
        print()

    # 建议
    if recommendations:
        print("── 优化建议 ──")
        for r in recommendations:
            icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(r["severity"], "⚪")
            print(f"  {icon} [{r['category']}] {r['issue']}")
            print(f"     → {r['recommendation']}")
        print()
    else:
        print("── 优化建议 ──")
        print("  ✅ 当前配置合理，无需调整")
        print()

    # 推荐配置
    print("── 推荐连接池配置 ──")
    print(f"  {'服务':25s} {'pool_size':>10} {'max_overflow':>13} {'timeout':>8}  {'说明'}")
    print(f"  {'-'*25} {'-'*10} {'-'*13} {'-'*8}  {'-'*20}")
    for svc, (ps, mo, pt, desc) in TUNING_RECOMMENDATIONS.items():
        print(f"  {svc:25s} {ps:>10} {mo:>13} {pt:>7}s  {desc}")
    print()


def main():
    parser = argparse.ArgumentParser(description="数据库连接池自动调优工具")
    parser.add_argument("--apply", action="store_true", help="应用建议到代码配置")
    parser.add_argument("--check", action="store_true", help="仅检查，不输出建议")
    parser.add_argument("--db-url", type=str, default=DEFAULT_PG_URL, help="PostgreSQL 连接串")
    args = parser.parse_args()

    db_url = args.db_url
    if "****" in db_url:
        db_url = os.getenv("DATABASE_URL", DEFAULT_PG_URL)

    # 检查连接
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            print(f"✓ PostgreSQL 连接成功: {str(version)[:60]}")
        engine.dispose()
    except Exception as e:
        print(f"✗ PostgreSQL 连接失败: {e}")
        print("提示: 请确保 PG 已启动，或通过 --db-url 指定连接串")
        return 1

    # 获取数据
    pg_settings = get_pg_settings(db_url)
    pool_stats = get_pool_stats(db_url)
    recommendations = analyze_and_recommend(pg_settings, pool_stats)

    if args.check:
        # 仅检查模式
        usage = pool_stats.get("usage_percent", 0)
        waiting = pool_stats.get("waiting_connections", 0)
        if usage > 80 or waiting > 0:
            print(f"WARNING: 连接使用率 {usage}%, 等待 {waiting}")
            return 1
        print("OK: 连接池状态正常")
        return 0

    print_report(pg_settings, pool_stats, recommendations)

    if args.apply:
        print("── 应用配置 ──")
        print("请手动将以下配置更新到相应文件:")
        print()
        print("  # database.py (Platform 主服务)")
        print('  _engine_kwargs.update({"pool_size": 20, "max_overflow": 40, "pool_timeout": 30})')
        print()
        print("  # scheduler_center/database.py (调度中心)")
        print('  _engine_kwargs.update({"pool_size": 15, "max_overflow": 30, "pool_timeout": 30})')
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
