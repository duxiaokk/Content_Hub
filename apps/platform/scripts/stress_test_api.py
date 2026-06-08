#!/usr/bin/env python3
"""
Ado_Jk Platform HTTP API 压力测试脚本

纯 stdlib 实现，零外部依赖（仅使用 threading, urllib, statistics）。
针对平台关键 API 端点发起并发压力，输出彩色终端报告和可选的 JSON 结果。

用法:
    python stress_test_api.py                              # 默认配置
    python stress_test_api.py --concurrency 200 --duration 120 --host 192.168.1.100
    python stress_test_api.py --json --output report.json  # 输出 JSON 报告

测试场景:
    GET  /                      主页（HTML）
    GET  /api/v1/posts          文章列表分页
    POST /api/v1/auth/login     登录认证
    GET  /health                健康检查
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

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
    """计算分位数。"""
    if not values:
        return 0.0
    s = sorted(values)
    idx = int((len(s) - 1) * p)
    return float(s[idx])


def _fmt_latency(ms: float) -> str:
    """格式化延迟，自动选择合适的颜色阈值。"""
    if ms < 50:
        color = GREEN
    elif ms < 200:
        color = YELLOW
    else:
        color = RED
    return f"{color}{ms:.2f}ms{RESET}"


# =========================================================================
# 数据模型
# =========================================================================


@dataclass
class RequestRecord:
    """单次 HTTP 请求的记录。"""
    scenario: str
    index: int
    status_code: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    body_size: int = 0
    timestamp: float = 0.0


@dataclass
class ScenarioConfig:
    """单个压测场景配置。"""
    name: str
    method: str
    path: str
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    expect_status: list[int] | None = None


@dataclass
class ScenarioReport:
    """单个场景的汇总报告。"""
    name: str
    total: int = 0
    success: int = 0
    fail: int = 0
    latencies: list[float] = field(default_factory=list)
    bps: float = 0.0  # bytes per second
    errors: list[str] = field(default_factory=list)
    status_dist: dict[int, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 0.0

    @property
    def tps(self) -> float:
        return self.success_rate / 100 * self.total / max(self.total / self.total, 1)
        # handled differently in the main report

    def summary(self) -> dict[str, Any]:
        lat = self.latencies if self.latencies else [0.0]
        return {
            "name": self.name,
            "total": self.total,
            "success": self.success,
            "fail": self.fail,
            "success_rate": round(self.success_rate, 2),
            "latency_p50_ms": round(_pctl(lat, 0.50), 2),
            "latency_p90_ms": round(_pctl(lat, 0.90), 2),
            "latency_p95_ms": round(_pctl(lat, 0.95), 2),
            "latency_p99_ms": round(_pctl(lat, 0.99), 2),
            "latency_avg_ms": round(statistics.fmean(lat), 2) if lat else 0,
            "latency_max_ms": round(max(lat), 2),
            "status_dist": self.status_dist,
        }


# =========================================================================
# HTTP Worker
# =========================================================================


def _build_request(config: ScenarioConfig, host: str) -> Request:
    """根据场景配置构造 urllib Request 对象。"""
    url = f"http://{host}{config.path}"
    headers = dict(config.headers or {})
    if config.body is not None and config.method == "POST":
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
    req = Request(url, headers=headers, method=config.method)
    if config.body is not None and config.method == "POST":
        data = json.dumps(config.body, ensure_ascii=False).encode("utf-8")
        req.data = data  # type: ignore[assignment]
    return req


def _execute_one(config: ScenarioConfig, host: str, timeout: int, index: int) -> RequestRecord:
    """执行单次 HTTP 请求并返回记录。"""
    record = RequestRecord(scenario=config.name, index=index, timestamp=time.perf_counter())
    req = _build_request(config, host)
    try:
        start = time.perf_counter()
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            latency = time.perf_counter() - start
            record.status_code = resp.status
            record.latency_ms = latency * 1000
            record.body_size = len(body)
    except URLError as exc:
        latency = time.perf_counter() - record.timestamp
        record.latency_ms = latency * 1000
        record.error = str(exc)
        record.status_code = -1
    except Exception as exc:
        latency = time.perf_counter() - record.timestamp
        record.latency_ms = latency * 1000
        record.error = str(exc)
        record.status_code = -1
    return record


# =========================================================================
# 压测引擎
# =========================================================================


class StressRunner:
    """并发压力测试执行器。"""

    def __init__(self, host: str, concurrency: int, duration: int, timeout: int):
        self.host = host
        self.concurrency = concurrency
        self.duration = duration
        self.timeout = timeout
        self.results: dict[str, list[RequestRecord]] = {}
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def run(self, scenarios: list[ScenarioConfig]) -> dict[str, list[RequestRecord]]:
        """发起并发压力测试。"""
        for sc in scenarios:
            self.results[sc.name] = []

        self._stop_event.clear()
        self.start_time = time.perf_counter()

        threads: list[threading.Thread] = []
        for sc in scenarios:
            for i in range(self.concurrency):
                t = threading.Thread(target=self._worker, args=(sc, i), daemon=True)
                threads.append(t)

        for t in threads:
            t.start()

        # 等待到达 duration 或所有线程结束
        deadline = self.start_time + self.duration
        while time.perf_counter() < deadline and not self._stop_event.is_set():
            time.sleep(0.1)

        self._stop_event.set()
        self.end_time = time.perf_counter()

        for t in threads:
            t.join(timeout=5)

        return self.results

    def _worker(self, scenario: ScenarioConfig, worker_idx: int):
        """工作线程：循环发送请求直到停止信号。"""
        count = 0
        while not self._stop_event.is_set():
            record = _execute_one(scenario, self.host, self.timeout, count)
            record.index = count
            with self._lock:
                self.results[scenario.name].append(record)
            count += 1


# =========================================================================
# 报告生成
# =========================================================================


def _generate_terminal_report(
    scenarios: list[ScenarioConfig],
    scenario_reports: list[ScenarioReport],
    total_records: int,
    elapsed: float,
    total_bytes: int,
) -> str:
    """生成彩色终端报告文本。"""
    lines: list[str] = []

    # — 标题 —
    lines.append("")
    lines.append(f"{BOLD}{CYAN}{'=' * 72}{RESET}")
    lines.append(f"{BOLD}{CYAN}  Ado_Jk Platform HTTP API 压力测试报告{RESET}")
    lines.append(f"{BOLD}{CYAN}{'=' * 72}{RESET}")
    lines.append(f"  目标地址  : {DIM}http://{_runner_host}{RESET}")
    lines.append(f"  并发数    : {BOLD}{_runner_concurrency}{RESET}")
    lines.append(f"  持续时间  : {BOLD}{_runner_duration}s{RESET}")
    lines.append(f"  总请求数  : {BOLD}{total_records}{RESET}")
    lines.append(f"  测试耗时  : {BOLD}{elapsed:.2f}s{RESET}")
    lines.append("")

    # — 全局概览 —
    all_lat = []
    all_success = 0
    for sr in scenario_reports:
        all_lat.extend(sr.latencies)
        all_success += sr.success
    overall_tps = total_records / elapsed if elapsed > 0 else 0
    overall_success_rate = all_success / total_records * 100 if total_records > 0 else 0

    lines.append(f"{BOLD}── 全局概览{RESET}")
    lines.append(f"  TPS (吞吐量)      : {BOLD}{overall_tps:.1f} req/s{RESET}")
    lines.append(f"  成功率             : {GREEN if overall_success_rate >= 99 else RED}"
                 f"{overall_success_rate:.2f}%{RESET}")
    if all_lat:
        lines.append(f"  平均延迟           : {_fmt_latency(statistics.fmean(all_lat))}")
        lines.append(f"  P50 延迟           : {_fmt_latency(_pctl(all_lat, 0.50))}")
        lines.append(f"  P90 延迟           : {_fmt_latency(_pctl(all_lat, 0.90))}")
        lines.append(f"  P95 延迟           : {_fmt_latency(_pctl(all_lat, 0.95))}")
        lines.append(f"  P99 延迟           : {_fmt_latency(_pctl(all_lat, 0.99))}")
        lines.append(f"  最大延迟           : {_fmt_latency(max(all_lat))}")
        lines.append(f"  标准差             : {DIM}{statistics.pstdev(all_lat):.2f}ms{RESET}")
    lines.append(f"  总传输量           : {total_bytes / 1024:,.1f} KB")
    lines.append("")

    # — 分场景报告 —
    lines.append(f"{BOLD}── 分场景详情{RESET}")
    for sr in scenario_reports:
        success_icon = f"{GREEN}PASS{RESET}" if sr.success_rate >= 99 else (
            f"{YELLOW}WARN{RESET}" if sr.success_rate >= 90 else f"{RED}FAIL{RESET}"
        )
        lines.append(f"  [{success_icon}] {BOLD}{sr.name}{RESET}")
        lines.append(f"      请求总数 : {sr.total}")
        lines.append(f"      成功/失败 : {sr.success}/{sr.fail}")
        lines.append(f"      成功率   : {sr.success_rate:.2f}%")
        if sr.latencies:
            lines.append(f"      平均延迟 : {_fmt_latency(statistics.fmean(sr.latencies))}")
            lines.append(f"      P50/P90/P95/P99 : "
                         f"{_fmt_latency(_pctl(sr.latencies, 0.50))} / "
                         f"{_fmt_latency(_pctl(sr.latencies, 0.90))} / "
                         f"{_fmt_latency(_pctl(sr.latencies, 0.95))} / "
                         f"{_fmt_latency(_pctl(sr.latencies, 0.99))}")
        if sr.errors:
            err_counter = Counter(sr.errors)
            top_err = err_counter.most_common(3)
            lines.append(f"      主要错误 :")
            for err_msg, cnt in top_err:
                lines.append(f"        [{RED}x{cnt}{RESET}] {err_msg[:80]}")
        lines.append("")

    # — 结论 —
    total_fail = sum(sr.fail for sr in scenario_reports)
    if total_fail == 0 and overall_success_rate >= 99:
        lines.append(f"{BOLD}{GREEN}  >>> 压力测试通过: 所有场景成功率 >= 99%{RESET}")
    elif overall_success_rate >= 90:
        lines.append(f"{BOLD}{YELLOW}  >>> 压力测试部分通过: 部分场景存在失败{RESET}")
    else:
        lines.append(f"{BOLD}{RED}  >>> 压力测试未通过: 成功率低于 90%{RESET}")
    lines.append(f"{BOLD}{CYAN}{'=' * 72}{RESET}")
    lines.append("")

    return "\n".join(lines)


def _generate_json_report(
    scenarios: list[ScenarioConfig],
    scenario_reports: list[ScenarioReport],
    total_records: int,
    elapsed: float,
    total_bytes: int,
) -> dict[str, Any]:
    """生成 JSON 格式报告。"""
    all_lat = []
    all_success = 0
    for sr in scenario_reports:
        all_lat.extend(sr.latencies)
        all_success += sr.success

    return {
        "meta": {
            "host": _runner_host,
            "concurrency": _runner_concurrency,
            "duration_seconds": _runner_duration,
            "elapsed_seconds": round(elapsed, 3),
            "total_requests": total_records,
            "total_bytes": total_bytes,
        },
        "overall": {
            "tps": round(total_records / elapsed, 2) if elapsed > 0 else 0,
            "success_rate": round(all_success / total_records * 100, 2) if total_records > 0 else 0,
            "latency_p50_ms": round(_pctl(all_lat, 0.50), 2),
            "latency_p90_ms": round(_pctl(all_lat, 0.90), 2),
            "latency_p95_ms": round(_pctl(all_lat, 0.95), 2),
            "latency_p99_ms": round(_pctl(all_lat, 0.99), 2),
            "latency_avg_ms": round(statistics.fmean(all_lat), 2) if all_lat else 0,
            "latency_max_ms": round(max(all_lat), 2) if all_lat else 0,
            "latency_stdev_ms": round(statistics.pstdev(all_lat), 2) if len(all_lat) > 1 else 0,
        },
        "scenarios": [sr.summary() for sr in scenario_reports],
    }


# =========================================================================
# 场景定义
# =========================================================================


def _get_default_scenarios() -> list[ScenarioConfig]:
    """默认测试场景集合。"""
    return [
        ScenarioConfig(
            name="GET / (Home)",
            method="GET",
            path="/",
            expect_status=[200, 302, 301],
            headers={"Accept": "text/html"},
        ),
        ScenarioConfig(
            name="GET /health",
            method="GET",
            path="/health",
            expect_status=[200],
            headers={"Accept": "application/json"},
        ),
        ScenarioConfig(
            name="GET /api/v1/posts",
            method="GET",
            path="/api/v1/posts?page=1&page_size=10",
            expect_status=[200],
            headers={"Accept": "application/json"},
        ),
        ScenarioConfig(
            name="POST /api/v1/auth/login",
            method="POST",
            path="/api/v1/auth/login",
            expect_status=[200, 401, 403, 422],
            body={"username": "Ado_Jk", "password": "admin"},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        ),
    ]


# =========================================================================
# 模块级状态（供报告函数使用）
# =========================================================================

_runner_host = "localhost"
_runner_concurrency = 100
_runner_duration = 60


# =========================================================================
# Main
# =========================================================================


def _print_banner():
    print(f"{BOLD}{CYAN}")
    print("   █████╗ ██████╗  ██████╗      ██╗██╗  ██╗")
    print("  ██╔══██╗██╔══██╗██╔═══██╗     ██║██║ ██╔╝")
    print("  ███████║██║  ██║██║   ██║     ██║█████╔╝ ")
    print("  ██╔══██║██║  ██║██║   ██║██   ██║██╔═██╗ ")
    print("  ██║  ██║██████╔╝╚██████╔╝╚█████╔╝██║  ██╗")
    print("  ╚═╝  ╚═╝╚═════╝  ╚═════╝  ╚════╝ ╚═╝  ╚═╝")
    print(f"         Platform Stress Test{RESET}")
    print()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ado_Jk Platform HTTP API 压力测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python stress_test_api.py
  python stress_test_api.py --concurrency 200 --duration 120
  python stress_test_api.py --host 192.168.1.100 --json --output report.json
        """,
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int, default=100,
        help="每个场景的并发线程数 (默认: 100)",
    )
    parser.add_argument(
        "--duration", "-d",
        type=int, default=60,
        help="压力测试持续时间（秒） (默认: 60)",
    )
    parser.add_argument(
        "--host", "-H",
        type=str, default="localhost:8000",
        help="目标平台地址，格式为 host:port (默认: localhost:8000)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int, default=10,
        help="每个 HTTP 请求的超时秒数 (默认: 10)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="同时输出 JSON 格式报告",
    )
    parser.add_argument(
        "--output", "-o",
        type=str, default=None,
        help="JSON 报告输出文件路径 (需配合 --json 使用)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="禁用彩色输出",
    )
    return parser


def main() -> int:
    global _runner_host, _runner_concurrency, _runner_duration, GREEN, RED, YELLOW, CYAN, MAGENTA, BOLD, RESET, DIM

    parser = build_argument_parser()
    args = parser.parse_args()

    if args.no_color:
        GREEN = RED = YELLOW = CYAN = MAGENTA = BOLD = RESET = DIM = ""

    _runner_host = args.host
    _runner_concurrency = args.concurrency
    _runner_duration = args.duration

    scenarios = _get_default_scenarios()

    _print_banner()
    print(f"  目标地址 : {DIM}http://{args.host}{RESET}")
    print(f"  并发数   : {BOLD}{args.concurrency}{RESET} 线程/场景  x  {len(scenarios)} 场景")
    print(f"  持续时间 : {BOLD}{args.duration}s{RESET}")
    print(f"  总线程数 : {BOLD}{args.concurrency * len(scenarios)}{RESET}")
    print()

    # — 连通性预检 —
    print(f"  {DIM}连通性预检...{RESET}")
    try:
        precheck_req = Request(f"http://{args.host}/health")
        with urlopen(precheck_req, timeout=args.timeout) as resp:
            precheck_status = resp.status
        if precheck_status == 200:
            print(f"  {GREEN}[OK]{RESET} 平台可达 (HTTP {precheck_status})")
        else:
            print(f"  {YELLOW}[WARN]{RESET} 平台响应 HTTP {precheck_status}, 继续测试...")
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET} 无法连接到 http://{args.host}: {e}")
        print(f"  {RED}请确认平台服务已启动后再运行本脚本。{RESET}")
        return 1

    print()
    print(f"  {BOLD}开始压力测试...{RESET} (按 Ctrl+C 可提前终止)")

    # — 运行压力测试 —
    runner = StressRunner(
        host=args.host,
        concurrency=args.concurrency,
        duration=args.duration,
        timeout=args.timeout,
    )
    try:
        results = runner.run(scenarios)
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}用户中断{RESET}")

    elapsed = runner.end_time - runner.start_time

    # — 汇总统计 —
    scenario_reports: list[ScenarioReport] = []
    total_records = 0
    total_bytes = 0

    for sc in scenarios:
        records = results.get(sc.name, [])
        sr = ScenarioReport(name=sc.name, total=len(records))
        for r in records:
            if r.status_code in range(200, 300):
                sr.success += 1
            elif r.error:
                sr.fail += 1
                sr.errors.append(r.error)
            else:
                sr.fail += 1
                sr.errors.append(f"HTTP {r.status_code}")
            sr.latencies.append(r.latency_ms)
            sr.body_size = max(sr.body_size, r.body_size)
        if records:
            sr.status_dist = dict(Counter(r.status_code for r in records))
        scenario_reports.append(sr)
        total_records += sr.total
        total_bytes += sum(r.body_size for r in records)

    # — 输出报告 —
    terminal_report = _generate_terminal_report(
        scenarios, scenario_reports, total_records, elapsed, total_bytes,
    )
    print(terminal_report)

    if args.json:
        json_report = _generate_json_report(
            scenarios, scenario_reports, total_records, elapsed, total_bytes,
        )
        json_str = json.dumps(json_report, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"  {GREEN}JSON 报告已保存至: {args.output}{RESET}")
        else:
            print(f"{DIM}── JSON 报告 ──{RESET}")
            print(json_str)

    # — 退出码 —
    total_fail = sum(sr.fail for sr in scenario_reports)
    if total_fail > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
