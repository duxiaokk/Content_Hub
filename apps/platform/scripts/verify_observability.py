#!/usr/bin/env python
"""可观测性端到端验证脚本

验证 OTel/Prometheus/Grafana/Loki/Jaeger 全链路是否正常工作。

用法:
    python scripts/verify_observability.py
    python scripts/verify_observability.py --host localhost
    python scripts/verify_observability.py --skip-grafana
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    DIM = "\033[2m"


def pass_msg(text: str) -> str:
    return f"{Colors.GREEN}[PASS]{Colors.RESET} {text}"


def fail_msg(text: str) -> str:
    return f"{Colors.RED}[FAIL]{Colors.RESET} {text}"


def warn_msg(text: str) -> str:
    return f"{Colors.YELLOW}[WARN]{Colors.RESET} {text}"


def info_msg(text: str) -> str:
    return f"{Colors.CYAN}[INFO]{Colors.RESET} {text}"


class ObservabilityVerifier:
    def __init__(self, host: str = "localhost", timeout: int = 5):
        self.host = host
        self.timeout = timeout
        self.results: list[dict] = []
        self.trace_id = f"verify-{int(time.time())}"

    def _http_get(self, url: str, expect_status: list | None = None) -> tuple[int, bytes, float]:
        if expect_status is None:
            expect_status = [200]
        req = Request(url, headers={"User-Agent": "ObsVerifier/1.0", "x-trace-id": self.trace_id})
        start = time.perf_counter()
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
                return resp.status, body, time.perf_counter() - start
        except URLError as e:
            return 0, b"", time.perf_counter() - start

    def check(self, name: str, url: str, validator=None, required: bool = True):
        """检查单个端点。"""
        try:
            status, body, latency = self._http_get(url)
            ok = 200 <= status < 300

            if validator:
                ok = ok and validator(body)

            detail = f"HTTP {status}, {latency*1000:.0f}ms"
            if not ok and required:
                detail += f" (url={url})"

            self.results.append({
                "name": name,
                "status": "pass" if ok else ("fail" if required else "warn"),
                "detail": detail,
                "latency_ms": round(latency * 1000, 1),
            })

            if ok:
                print(pass_msg(f"{name}: {detail}"))
            elif required:
                print(fail_msg(f"{name}: {detail}"))
            else:
                print(warn_msg(f"{name}: {detail}"))
            return ok
        except Exception as e:
            self.results.append({
                "name": name,
                "status": "fail" if required else "warn",
                "detail": str(e),
                "latency_ms": 0,
            })
            if required:
                print(fail_msg(f"{name}: {e}"))
            else:
                print(warn_msg(f"{name}: {e}"))
            return False

    # ------------------------------------------------------------------
    # 验证项
    # ------------------------------------------------------------------

    def verify_prometheus(self):
        """验证 Prometheus。"""
        print(f"\n{Colors.BOLD}── Prometheus{Colors.RESET}")
        base = f"http://{self.host}:9090"

        self.check("Prometheus /-/healthy", f"{base}/-/healthy")

        # Targets
        try:
            _, body, _ = self._http_get(f"{base}/api/v1/targets")
            data = json.loads(body)
            targets_up = sum(1 for t in data.get("data", {}).get("activeTargets", []) if t.get("health") == "up")
            total = len(data.get("data", {}).get("activeTargets", []))
            print(info_msg(f"  Targets: {targets_up}/{total} UP"))
        except Exception:
            print(warn_msg("  Could not check targets"))

        # 指标
        self.check("Prometheus /metrics", f"{base}/metrics")

    def verify_grafana(self):
        """验证 Grafana。"""
        print(f"\n{Colors.BOLD}── Grafana{Colors.RESET}")
        base = f"http://{self.host}:3000"

        self.check("Grafana /api/health", f"{base}/api/health")

        # 数据源
        try:
            _, body, _ = self._http_get(f"{base}/api/datasources")
            datasources = json.loads(body)
            print(info_msg(f"  Datasources: {len(datasources)} configured"))
        except Exception:
            print(warn_msg("  Could not check datasources (auth required)"))

    def verify_jaeger(self):
        """验证 Jaeger。"""
        print(f"\n{Colors.BOLD}── Jaeger (Distributed Tracing){Colors.RESET}")
        base = f"http://{self.host}:16686"

        self.check("Jaeger /api/services", f"{base}/api/services")

        # 服务列表
        try:
            _, body, _ = self._http_get(f"{base}/api/services")
            data = json.loads(body)
            services = data.get("data", [])
            if services:
                print(info_msg(f"  Services reporting traces: {', '.join(services)}"))
            else:
                print(warn_msg("  No services reporting traces yet"))
        except Exception:
            pass

        # OTLP gRPC endpoint (TCP check)
        try:
            import socket
            sock = socket.create_connection((self.host, 4317), timeout=self.timeout)
            sock.close()
            print(pass_msg("Jaeger OTLP gRPC endpoint (4317): reachable"))
        except Exception as e:
            print(fail_msg(f"Jaeger OTLP gRPC endpoint (4317): {e}"))

    def verify_loki(self):
        """验证 Loki。"""
        print(f"\n{Colors.BOLD}── Loki (Log Aggregation){Colors.RESET}")
        base = f"http://{self.host}:3100"

        self.check("Loki /ready", f"{base}/ready")

        # 查询测试
        try:
            query_url = f"{base}/loki/api/v1/query_range?query={{job=~'.+'}}&limit=1"
            self.check("Loki query test", query_url, required=False)
        except Exception:
            pass

    def verify_platform_metrics(self):
        """验证 Platform 的 /metrics 端点。"""
        print(f"\n{Colors.BOLD}── Platform Metrics{Colors.RESET}")

        for port, name in [(8000, "Platform"), (8010, "Scheduler API")]:
            url = f"http://{self.host}:{port}/metrics"
            try:
                _, body, _ = self._http_get(url)
                metrics = body.decode()
                has_http_requests = "http_requests_total" in metrics or "http_request_duration" in metrics
                has_custom = "agent_" in metrics or "scheduler_" in metrics or "orchestration_" in metrics
                line_count = metrics.count("\n")
                status = "pass" if line_count > 5 else "warn"
                print(pass_msg(f"{name} /metrics: {line_count} metrics lines") if status == "pass"
                      else warn_msg(f"{name} /metrics: only {line_count} lines"))
            except Exception as e:
                print(warn_msg(f"{name} /metrics: {e}"))

    def verify_trace_propagation(self):
        """验证 trace_id 跨服务传播。"""
        print(f"\n{Colors.BOLD}── Trace Propagation{Colors.RESET}")
        print(info_msg(f"  Test trace_id: {self.trace_id}"))

        # 通过 Platform 触发一个请求
        try:
            url = f"http://{self.host}:8000/"
            status, _, latency = self._http_get(url)
            print(info_msg(f"  Platform root: HTTP {status}, {latency*1000:.0f}ms"))
            print(info_msg(f"  检查 Jaeger UI (http://{self.host}:16686) 搜索 trace_id={self.trace_id}"))
        except Exception as e:
            print(warn_msg(f"  Could not trigger trace: {e}"))

    def verify_log_correlation(self):
        """验证日志与 trace 关联。"""
        print(f"\n{Colors.BOLD}── Log-Trace Correlation{Colors.RESET}")

        # 通过 Scheduler API 触发
        try:
            url = f"http://{self.host}:8010/health"
            self._http_get(url)
            print(info_msg(f"  Triggered scheduler health check with trace_id={self.trace_id}"))
            print(info_msg(f"  检查 Loki (http://{self.host}:3100) 按 trace_id={self.trace_id} 过滤日志"))
        except Exception as e:
            print(warn_msg(f"  Scheduler not reachable: {e}"))

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def run(self, skip_grafana: bool = False):
        print()
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}  Ado_Jk Platform — 可观测性端到端验证{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
        print()

        self.verify_prometheus()
        if not skip_grafana:
            self.verify_grafana()
        self.verify_jaeger()
        self.verify_loki()
        self.verify_platform_metrics()
        self.verify_trace_propagation()
        self.verify_log_correlation()

        # 报告
        print()
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        passed = sum(1 for r in self.results if r["status"] == "pass")
        failed = sum(1 for r in self.results if r["status"] == "fail")
        warned = sum(1 for r in self.results if r["status"] == "warn")
        total = len(self.results)
        color = Colors.GREEN if failed == 0 else Colors.RED
        print(f"  Results: {color}{passed}/{total} passed{Colors.RESET}", end="")
        if failed > 0:
            print(f", {Colors.RED}{failed} failed{Colors.RESET}", end="")
        if warned > 0:
            print(f", {Colors.YELLOW}{warned} warned{Colors.RESET}", end="")
        print()
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        print()

        return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="可观测性端到端验证")
    parser.add_argument("--host", default="localhost", help="服务主机名")
    parser.add_argument("--timeout", type=int, default=5, help="HTTP 超时秒数")
    parser.add_argument("--skip-grafana", action="store_true", help="跳过 Grafana 检查")
    args = parser.parse_args()

    verifier = ObservabilityVerifier(host=args.host, timeout=args.timeout)
    return verifier.run(skip_grafana=args.skip_grafana)


if __name__ == "__main__":
    raise SystemExit(main())
