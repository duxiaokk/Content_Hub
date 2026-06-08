#!/usr/bin/env python3
"""
Ado_Jk Platform 编排端到端压力测试脚本

并发提交 N 个编排运行，每个运行包含 3~5 个任务，
测量规划时间、任务分发时间、聚合时间和成功率，
输出时间线报告与逐运行明细。

依赖:
    httpx (已在 requirements.txt 中)

用法:
    python stress_test_orchestration.py
    python stress_test_orchestration.py --scheduler-url http://127.0.0.1:8010 --runs 30 --concurrency 10
    python stress_test_orchestration.py --token my-token --json -o report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

# =========================================================================
# ANSI Escape Codes
# =========================================================================

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"


def _pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int((len(s) - 1) * p)
    return float(s[idx])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================================================================
# 数据模型
# =========================================================================


@dataclass
class RunRecord:
    """单个编排运行的全量记录。"""
    index: int
    run_id: str = ""
    trace_id: str = ""
    intent: str = ""
    intent_name: str = ""
    num_tasks: int = 0

    # 阶段耗时 (秒)
    planning_time_s: float = 0.0    # 从提交到获得 run_id 的时间
    submit_time_s: float = 0.0       # submit POST 请求耗时
    task_dispatch_time_s: float = 0.0  # 首任务被分发的时间 (近似)
    aggregation_time_s: float = 0.0   # 最后一个任务完成到聚合结束的时间 (近似)
    total_e2e_time_s: float = 0.0     # 提交完成到终态的总时间

    # 轮询阶段详情
    first_task_at: float = 0.0          # 相对时间: 首个任务完成 (从提交开始)
    last_task_at: float = 0.0           # 相对时间: 最后一个任务完成
    aggregation_start_at: float = 0.0   # 相对时间: 聚合开始
    finished_at: float = 0.0            # 相对时间: 终态

    # 任务状态明细
    total_tasks: int = 0
    succeeded_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0

    # 终态
    final_status: str = "UNKNOWN"
    last_error: str | None = None

    # 轮询统计
    poll_count: int = 0
    poll_interval_s: float = 1.0

    # 原始提交时间戳 (perf_counter)
    submit_started: float = 0.0
    submit_done: float = 0.0


@dataclass
class OrchestrationReport:
    """编排压测汇总报告。"""
    total_runs: int
    succeeded_runs: int
    failed_runs: int
    timeout_runs: int
    cancelled_runs: int

    # 各阶段分位数 (秒)
    planning_p50: float = 0.0
    planning_p95: float = 0.0
    dispatch_p50: float = 0.0
    dispatch_p95: float = 0.0
    aggregation_p50: float = 0.0
    aggregation_p95: float = 0.0
    e2e_p50: float = 0.0
    e2e_p95: float = 0.0

    # 任务级别
    total_tasks: int = 0
    task_success_rate: float = 0.0

    run_records: list[RunRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "succeeded_runs": self.succeeded_runs,
            "failed_runs": self.failed_runs,
            "timeout_runs": self.timeout_runs,
            "cancelled_runs": self.cancelled_runs,
            "planning_p50_s": round(self.planning_p50, 3),
            "planning_p95_s": round(self.planning_p95, 3),
            "dispatch_p50_s": round(self.dispatch_p50, 3),
            "dispatch_p95_s": round(self.dispatch_p95, 3),
            "aggregation_p50_s": round(self.aggregation_p50, 3),
            "aggregation_p95_s": round(self.aggregation_p95, 3),
            "e2e_p50_s": round(self.e2e_p50, 3),
            "e2e_p95_s": round(self.e2e_p95, 3),
            "total_tasks": self.total_tasks,
            "task_success_rate": round(self.task_success_rate, 2),
            "runs": [
                {
                    "index": r.index,
                    "run_id": r.run_id,
                    "intent": r.intent_name,
                    "num_tasks": r.num_tasks,
                    "final_status": r.final_status,
                    "planning_time_s": round(r.planning_time_s, 3),
                    "total_e2e_time_s": round(r.total_e2e_time_s, 3),
                    "succeeded_tasks": r.succeeded_tasks,
                    "failed_tasks": r.failed_tasks,
                    "skipped_tasks": r.skipped_tasks,
                    "poll_count": r.poll_count,
                    "error": r.last_error,
                }
                for r in self.run_records
            ],
        }


# =========================================================================
# 场景数据
# =========================================================================

_ORCHESTRATION_INTENTS = [
    {"name": "blog-seo-optimize", "intent": "分析博客文章的 SEO 表现，生成标题优化建议和 meta 描述", "task_count": 3},
    {"name": "content-moderation", "intent": "审核最新评论，标记不当言论，生成审核报告", "task_count": 4},
    {"name": "weekly-digest", "intent": "汇总本周发布的文章，提取热门话题，生成周报摘要", "task_count": 5},
    {"name": "tag-cleanup", "intent": "扫描所有文章的标签，合并相似标签，清理过时标签", "task_count": 3},
    {"name": "analytics-report", "intent": "分析平台访问数据，生成流量报告和用户行为洞察", "task_count": 4},
    {"name": "content-backup", "intent": "备份今日所有文章内容到归档存储，生成备份清单", "task_count": 3},
    {"name": "quality-audit", "intent": "审查文章质量评分，标记低分文章，推荐改进方向", "task_count": 5},
    {"name": "auto-translate", "intent": "将本周新文章翻译为英文版本，保持 Markdown 格式", "task_count": 4},
    {"name": "sitemap-regenerate", "intent": "重新生成网站 Sitemap XML，提交给搜索引擎", "task_count": 3},
    {"name": "dead-link-check", "intent": "扫描所有文章中的外部链接，检测死链并生成修复报告", "task_count": 4},
]


def _pick_intent(index: int) -> dict[str, Any]:
    """轮替选取编排意图。"""
    return _ORCHESTRATION_INTENTS[index % len(_ORCHESTRATION_INTENTS)]


# =========================================================================
# HTTP 操作
# =========================================================================


async def _submit_run(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    intent_info: dict[str, Any],
    index: int,
    timeout: float,
) -> RunRecord:
    """提交一个编排运行。"""
    record = RunRecord(
        index=index,
        intent=intent_info["intent"],
        intent_name=intent_info["name"],
        num_tasks=intent_info["task_count"],
        trace_id=str(uuid.uuid4()),
    )

    headers = {
        "x-internal-token": token,
        "x-trace-id": record.trace_id,
        "Content-Type": "application/json",
    }
    body = {
        "name": f"stress-test-{intent_info['name']}-{index}",
        "intent": intent_info["intent"],
        "context": {
            "source": "stress_test_orchestration",
            "index": index,
            "timestamp": _now_iso(),
        },
        "constraints": {
            "max_duration_seconds": 120,
            "max_parallel_tasks": 3,
        },
        "trace_id": record.trace_id,
    }

    record.submit_started = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/api/internal/orchestration/runs",
            json=body,
            headers=headers,
            timeout=timeout,
        )
        record.submit_done = time.perf_counter()
        record.submit_time_s = record.submit_done - record.submit_started

        if resp.status_code in range(200, 300):
            data = resp.json()
            record.run_id = data.get("run_id", "")
            record.total_tasks = data.get("total_tasks", intent_info["task_count"])
            record.planning_time_s = record.submit_time_s
        else:
            record.submit_time_s = time.perf_counter() - record.submit_started
            record.final_status = "SUBMIT_FAILED"
            record.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            record.finished_at = time.perf_counter() - record.submit_started
    except Exception as e:
        record.submit_done = time.perf_counter()
        record.submit_time_s = record.submit_done - record.submit_started
        record.final_status = "SUBMIT_FAILED"
        record.last_error = str(e)
        record.finished_at = record.submit_time_s

    return record


async def _poll_until_terminal(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    record: RunRecord,
    poll_interval: float,
    deadline: float,
) -> RunRecord:
    """轮询编排运行直到终态或超时。"""
    if not record.run_id or record.final_status == "SUBMIT_FAILED":
        return record

    headers = {"x-internal-token": token}

    while time.perf_counter() < deadline:
        record.poll_count += 1
        try:
            resp = await client.get(
                f"{base_url}/api/internal/orchestration/runs/{record.run_id}",
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")

                # 更新任务计数
                record.total_tasks = data.get("total_tasks", record.total_tasks)
                record.succeeded_tasks = data.get("succeeded_tasks", 0)
                record.failed_tasks = data.get("failed_tasks", 0)
                record.skipped_tasks = data.get("skipped_tasks", 0)

                # 检测首任务完成 (succeeded >= 1 且尚未记录过)
                if record.succeeded_tasks >= 1 and record.first_task_at == 0:
                    record.first_task_at = time.perf_counter() - record.submit_started

                # 检测聚合开始 = 全部任务完成但 run 仍在 managed/succeeding
                all_tasks_done = (
                    record.succeeded_tasks + record.failed_tasks + record.skipped_tasks
                ) >= record.total_tasks
                if all_tasks_done and record.aggregation_start_at == 0:
                    record.aggregation_start_at = time.perf_counter() - record.submit_started
                    record.last_task_at = record.aggregation_start_at

                # 终态检查
                terminal_statuses = {"SUCCEEDED", "FAILED", "PARTIAL", "CANCELED"}
                if status.upper() in terminal_statuses:
                    record.finished_at = time.perf_counter() - record.submit_started
                    record.total_e2e_time_s = record.finished_at
                    record.final_status = status.upper()

                    # 后计算各阶段耗时
                    # 计划时间 = submit 耗时 (已在 _submit_run 记录)
                    # 任务分发时间 = 首任务完成 - 提交完成
                    if record.first_task_at > 0:
                        record.task_dispatch_time_s = record.first_task_at
                    # 聚合时间 = finished - aggregation_start
                    if record.aggregation_start_at > 0:
                        record.aggregation_time_s = record.finished_at - record.aggregation_start_at

                    record.last_error = data.get("last_error")
                    return record
            else:
                # 如果返回 404，可能 run 尚未入库，继续等
                pass
        except Exception as e:
            # 临时错误：继续轮询
            pass

        await asyncio.sleep(poll_interval)

    # 超时
    record.finished_at = time.perf_counter() - record.submit_started
    record.total_e2e_time_s = record.finished_at
    record.final_status = "TIMEOUT"
    record.last_error = f"Polling timed out after {record.poll_count} polls"
    return record


# =========================================================================
# 压测执行器
# =========================================================================


async def run_orchestration_stress(
    base_url: str,
    token: str,
    total_runs: int,
    concurrency: int,
    poll_interval: float,
    max_e2e_timeout: float,
    http_timeout: float,
) -> OrchestrationReport:
    """执行编排压力测试。"""
    limits = httpx.Limits(
        max_connections=max(concurrency * 5, 100),
        max_keepalive_connections=100,
    )
    client_timeout = httpx.Timeout(http_timeout)

    async with httpx.AsyncClient(
        limits=limits,
        timeout=client_timeout,
        trust_env=False,
    ) as client:
        sem = asyncio.Semaphore(concurrency)

        # — 阶段 1: 并发提交所有编排运行 —
        async def _submit_wrapped(index: int) -> RunRecord:
            async with sem:
                intent_info = _pick_intent(index)
                return await _submit_run(
                    client, base_url, token, intent_info, index, http_timeout,
                )

        submit_start = time.perf_counter()
        records = await asyncio.gather(*[_submit_wrapped(i) for i in range(total_runs)])
        submit_end = time.perf_counter()

        # — 阶段 2: 并发轮询直到终态 —
        async def _poll_wrapped(record: RunRecord) -> RunRecord:
            async with sem:
                deadline = record.submit_done + max_e2e_timeout
                return await _poll_until_terminal(
                    client, base_url, token, record, poll_interval, deadline,
                )

        poll_start = time.perf_counter()
        records = await asyncio.gather(*[_poll_wrapped(r) for r in records])
        poll_end = time.perf_counter()

    # — 汇总统计 —
    succeeded = [r for r in records if r.final_status == "SUCCEEDED"]
    partial = [r for r in records if r.final_status == "PARTIAL"]
    failed = [r for r in records if r.final_status in ("FAILED", "SUBMIT_FAILED")]
    timed_out = [r for r in records if r.final_status == "TIMEOUT"]
    cancelled = [r for r in records if r.final_status == "CANCELED"]

    planning_times = [r.planning_time_s for r in records if r.planning_time_s > 0]
    dispatch_times = [r.task_dispatch_time_s for r in records if r.task_dispatch_time_s > 0]
    aggregation_times = [r.aggregation_time_s for r in records if r.aggregation_time_s > 0]
    e2e_times = [r.total_e2e_time_s for r in records if r.total_e2e_time_s > 0]

    total_tasks = sum(r.total_tasks for r in records)
    succeeded_tasks = sum(r.succeeded_tasks for r in records)

    report = OrchestrationReport(
        total_runs=total_runs,
        succeeded_runs=len(succeeded),
        failed_runs=len(failed) + len(timed_out),
        timeout_runs=len(timed_out),
        cancelled_runs=len(cancelled),
        planning_p50=_pctl(planning_times, 0.50) if planning_times else 0,
        planning_p95=_pctl(planning_times, 0.95) if planning_times else 0,
        dispatch_p50=_pctl(dispatch_times, 0.50) if dispatch_times else 0,
        dispatch_p95=_pctl(dispatch_times, 0.95) if dispatch_times else 0,
        aggregation_p50=_pctl(aggregation_times, 0.50) if aggregation_times else 0,
        aggregation_p95=_pctl(aggregation_times, 0.95) if aggregation_times else 0,
        e2e_p50=_pctl(e2e_times, 0.50) if e2e_times else 0,
        e2e_p95=_pctl(e2e_times, 0.95) if e2e_times else 0,
        total_tasks=total_tasks,
        task_success_rate=(succeeded_tasks / total_tasks * 100) if total_tasks > 0 else 0,
        run_records=records,
    )

    return report


# =========================================================================
# 终端报告
# =========================================================================


def _print_terminal_report(
    report: OrchestrationReport,
    base_url: str,
    total_runs: int,
    concurrency: int,
    elapsed_s: float,
    submit_window_s: float,
) -> None:
    """打印彩色终端报告。"""
    print()
    print(f"{BOLD}{CYAN}{'=' * 72}{RESET}")
    print(f"{BOLD}{CYAN}  Ado_Jk Platform 编排端到端压力测试报告{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 72}{RESET}")
    print(f"  调度中心    : {DIM}{base_url}{RESET}")
    print(f"  编排运行数  : {BOLD}{total_runs}{RESET}")
    print(f"  并发度      : {BOLD}{concurrency}{RESET}")
    print(f"  总耗时      : {BOLD}{elapsed_s:.2f}s{RESET}")
    print(f"  提交窗口    : {DIM}{submit_window_s:.2f}s{RESET}")
    print()

    # — 运行结果 —
    print(f"{BOLD}── 运行结果{RESET}")
    print(f"  成功        : {GREEN}{report.succeeded_runs}{RESET}")
    if report.failed_runs > 0:
        print(f"  失败        : {RED}{report.failed_runs}{RESET}")
    else:
        print(f"  失败        : 0")
    if report.timeout_runs > 0:
        print(f"  超时        : {YELLOW}{report.timeout_runs}{RESET}")
    if report.cancelled_runs > 0:
        print(f"  已取消      : {YELLOW}{report.cancelled_runs}{RESET}")
    success_rate = report.succeeded_runs / total_runs * 100 if total_runs > 0 else 0
    color = GREEN if success_rate >= 90 else (YELLOW if success_rate >= 70 else RED)
    print(f"  运行成功率  : {color}{success_rate:.1f}%{RESET}")
    print()

    # — 阶段耗时 —
    print(f"{BOLD}── 阶段耗时 (秒){RESET}")
    print(f"  规划 (Planning)       P50={report.planning_p50:.3f}s  P95={report.planning_p95:.3f}s")
    print(f"  任务分发 (Dispatch)   P50={report.dispatch_p50:.3f}s  P95={report.dispatch_p95:.3f}s")
    print(f"  聚合 (Aggregation)    P50={report.aggregation_p50:.3f}s  P95={report.aggregation_p95:.3f}s")
    print(f"  端到端 (E2E)          P50={report.e2e_p50:.3f}s  P95={report.e2e_p95:.3f}s")
    print()

    # — 任务级别 —
    print(f"{BOLD}── 任务级别统计{RESET}")
    print(f"  总任务数    : {report.total_tasks}")
    task_rate_color = GREEN if report.task_success_rate >= 95 else (YELLOW if report.task_success_rate >= 80 else RED)
    print(f"  任务成功率  : {task_rate_color}{report.task_success_rate:.1f}%{RESET}")
    print()

    # — 逐运行时间线 —
    print(f"{BOLD}── 时间线 (逐运行明细){RESET}")
    print(f"  {'#':>3s}  {'Run ID':<10s}  {'Intent':<22s}  {'Status':<14s}  {'Plan':>6s}  {'Dispatch':>8s}  {'Aggr':>6s}  {'E2E':>7s}  {'Tasks':>6s}")
    print(f"  {'-' * 3}  {'-' * 10}  {'-' * 22}  {'-' * 14}  {'-' * 6}  {'-' * 8}  {'-' * 6}  {'-' * 7}  {'-' * 6}")
    for r in report.run_records:
        run_id_short = r.run_id[:10] if r.run_id else "(no id)"
        intent_short = r.intent_name[:20]
        status_color = GREEN if r.final_status == "SUCCEEDED" else (
            YELLOW if r.final_status == "PARTIAL" else RED
        )
        status_short = r.final_status[:12]
        print(
            f"  {r.index:>3d}  {run_id_short:<10s}  {intent_short:<22s}  "
            f"{status_color}{status_short:<14s}{RESET}  "
            f"{r.planning_time_s:>5.2f}s  "
            f"{r.task_dispatch_time_s:>7.2f}s  "
            f"{r.aggregation_time_s:>5.2f}s  "
            f"{r.total_e2e_time_s:>6.2f}s  "
            f"{r.succeeded_tasks}/{r.total_tasks}"
        )
        if r.last_error:
            print(f"       {DIM}Error: {r.last_error[:100]}{RESET}")
    print()

    # — E2E 分布 —
    e2e_vals = [r.total_e2e_time_s for r in report.run_records if r.total_e2e_time_s > 0]
    if e2e_vals:
        print(f"{BOLD}── E2E 延迟分布 (秒){RESET}")
        print(f"  Min={min(e2e_vals):.2f}  P50={_pctl(e2e_vals, 0.50):.2f}  "
              f"P90={_pctl(e2e_vals, 0.90):.2f}  P95={_pctl(e2e_vals, 0.95):.2f}  "
              f"P99={_pctl(e2e_vals, 0.99):.2f}  Max={max(e2e_vals):.2f}")
        print(f"  Mean={statistics.fmean(e2e_vals):.2f}  "
              f"Stdev={statistics.pstdev(e2e_vals):.2f}" if len(e2e_vals) > 1 else "")
        print()

    # — 结论 —
    if report.failed_runs == 0 and report.timeout_runs == 0:
        print(f"{BOLD}{GREEN}  >>> 编排压力测试通过: 所有运行成功完成{RESET}")
    elif success_rate >= 90:
        print(f"{BOLD}{YELLOW}  >>> 编排压力测试部分通过: {success_rate:.1f}% 运行成功{RESET}")
    else:
        print(f"{BOLD}{RED}  >>> 编排压力测试未通过: 仅 {success_rate:.1f}% 运行成功{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 72}{RESET}")
    print()


# =========================================================================
# Main
# =========================================================================


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ado_Jk Platform 编排端到端压力测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python stress_test_orchestration.py
  python stress_test_orchestration.py --scheduler-url http://127.0.0.1:8010 --runs 30 --concurrency 10
  python stress_test_orchestration.py --json -o orchestration_report.json
        """,
    )
    parser.add_argument(
        "--scheduler-url",
        type=str,
        default=os.getenv("SCHEDULER_URL", "http://127.0.0.1:8010"),
        help="Scheduler Center 地址 (默认: http://127.0.0.1:8010)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.getenv("SCHEDULER_INTERNAL_TOKEN", "local-dev-scheduler-token"),
        help="调度中心内部 Token",
    )
    parser.add_argument(
        "--runs", "-n",
        type=int, default=20,
        help="编排运行总数 (默认: 20)",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int, default=10,
        help="并发提交/轮询数 (默认: 10)",
    )
    parser.add_argument(
        "--poll-interval", "-p",
        type=float, default=1.0,
        help="轮询间隔秒数 (默认: 1.0)",
    )
    parser.add_argument(
        "--e2e-timeout",
        type=float, default=300.0,
        help="单个运行的 E2E 超时秒数 (默认: 300)",
    )
    parser.add_argument(
        "--http-timeout",
        type=float, default=60.0,
        help="单次 HTTP 请求超时秒数 (默认: 60)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="同时输出 JSON 格式报告",
    )
    parser.add_argument(
        "--output", "-o",
        type=str, default=None,
        help="JSON 报告输出文件路径",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="禁用彩色输出",
    )
    return parser


def _print_banner():
    print(f"{BOLD}{CYAN}")
    print("   █████╗ ██████╗  ██████╗      ██╗██╗  ██╗")
    print("  ██╔══██╗██╔══██╗██╔═══██╗     ██║██║ ██╔╝")
    print("  ███████║██║  ██║██║   ██║     ██║█████╔╝ ")
    print("  ██╔══██║██║  ██║██║   ██║██   ██║██╔═██╗ ")
    print("  ██║  ██║██████╔╝╚██████╔╝╚█████╔╝██║  ██╗")
    print("  ╚═╝  ╚═╝╚═════╝  ╚═════╝  ╚════╝ ╚═╝  ╚═╝")
    print(f"     Orchestration End-to-End Stress Test{RESET}")
    print()


async def async_main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    global GREEN, RED, YELLOW, CYAN, MAGENTA, BOLD, RESET, DIM
    if args.no_color:
        GREEN = RED = YELLOW = CYAN = MAGENTA = BOLD = RESET = DIM = ""

    base_url = args.scheduler_url.rstrip("/")
    token = args.token

    _print_banner()
    print(f"  调度中心   : {DIM}{base_url}{RESET}")
    print(f"  编排运行数 : {BOLD}{args.runs}{RESET}")
    print(f"  并发度     : {BOLD}{args.concurrency}{RESET}")
    print(f"  E2E 超时   : {BOLD}{args.e2e_timeout}s{RESET}")
    print()

    # — 连通性预检 —
    print(f"  {DIM}连通性预检...{RESET}")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), trust_env=False) as client:
            resp = await client.get(
                f"{base_url}/api/internal/orchestration/runs",
                headers={"x-internal-token": token},
            )
            if resp.status_code == 200:
                print(f"  {GREEN}[OK]{RESET} 调度中心可达 (HTTP {resp.status_code})")
            else:
                print(f"  {YELLOW}[WARN]{RESET} 调度中心响应 HTTP {resp.status_code}, 继续测试...")
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET} 无法连接到 {base_url}: {e}")
        print(f"  {RED}请确认调度中心已启动后再运行本脚本。{RESET}")
        return 1

    print()
    print(f"  {BOLD}开始编排压力测试...{RESET} (按 Ctrl+C 可提前终止)")
    print()

    # — 执行压测 —
    overall_start = time.perf_counter()
    try:
        report = await run_orchestration_stress(
            base_url=base_url,
            token=token,
            total_runs=args.runs,
            concurrency=args.concurrency,
            poll_interval=args.poll_interval,
            max_e2e_timeout=args.e2e_timeout,
            http_timeout=args.http_timeout,
        )
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}用户中断{RESET}")
        return 130
    overall_end = time.perf_counter()
    elapsed_s = overall_end - overall_start

    # 计算提交窗口 (从第一个提交开始到最后一个提交完成)
    submit_times = [r.submit_done - r.submit_started for r in report.run_records]
    submit_window_s = (max(r.submit_done for r in report.run_records) -
                       min(r.submit_started for r in report.run_records))

    # — 打印终端报告 —
    _print_terminal_report(
        report=report,
        base_url=base_url,
        total_runs=args.runs,
        concurrency=args.concurrency,
        elapsed_s=elapsed_s,
        submit_window_s=submit_window_s,
    )

    # — JSON 输出 —
    if args.json:
        json_data = report.to_dict()
        json_data["meta"] = {
            "scheduler_url": base_url,
            "total_runs": args.runs,
            "concurrency": args.concurrency,
            "elapsed_s": round(elapsed_s, 3),
            "submit_window_s": round(submit_window_s, 3),
            "timestamp": _now_iso(),
        }
        json_str = json.dumps(json_data, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"  {GREEN}JSON 报告已保存至: {args.output}{RESET}")
        else:
            print(f"{DIM}── JSON 报告 ──{RESET}")
            print(json_str)

    # — 退出码 —
    if report.failed_runs > 0 or report.timeout_runs > 0:
        return 1
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
