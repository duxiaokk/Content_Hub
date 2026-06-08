#!/usr/bin/env python3
"""
Ado_Jk Platform 容器部署冒烟测试脚本

用法:
    python smoke_test.py                          # 使用默认配置
    PLATFORM_HOST=192.168.1.100 TIMEOUT=10 python smoke_test.py  # 自定义配置

环境变量 (均有默认值):
    PLATFORM_HOST, PLATFORM_PORT
    SCHEDULER_HOST, SCHEDULER_PORT
    POSTGRES_HOST, POSTGRES_PORT
    REDIS_HOST, REDIS_PORT
    JAEGER_HOST, JAEGER_PORT
    PROMETHEUS_HOST, PROMETHEUS_PORT
    LOKI_HOST, LOKI_PORT
    GRAFANA_HOST, GRAFANA_PORT
    TIMEOUT
"""

import json
import os
import socket
import sys
import time
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.request import Request, urlopen

# ── ANSI Escape Codes ──────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"


def color_pass(text: str) -> str:
    return f"{GREEN}[PASS]{RESET} {text}"


def color_fail(text: str) -> str:
    return f"{RED}[FAIL]{RESET} {text}"


def color_warn(text: str) -> str:
    return f"{YELLOW}[WARN]{RESET} {text}"


def color_skip(text: str) -> str:
    return f"{YELLOW}[SKIP]{RESET} {text}"


# ── Configuration ──────────────────────────────────────────────────


@dataclass
class Config:
    platform_host: str = "localhost"
    platform_port: int = 8000
    scheduler_host: str = "localhost"
    scheduler_port: int = 8010
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    redis_host: str = "localhost"
    redis_port: int = 6379
    jaeger_host: str = "localhost"
    jaeger_port: int = 16686
    prometheus_host: str = "localhost"
    prometheus_port: int = 9090
    loki_host: str = "localhost"
    loki_port: int = 3100
    grafana_host: str = "localhost"
    grafana_port: int = 3000
    timeout: int = 5  # seconds

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            platform_host=os.getenv("PLATFORM_HOST", "localhost"),
            platform_port=int(os.getenv("PLATFORM_PORT", "8000")),
            scheduler_host=os.getenv("SCHEDULER_HOST", "localhost"),
            scheduler_port=int(os.getenv("SCHEDULER_PORT", "8010")),
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            jaeger_host=os.getenv("JAEGER_HOST", "localhost"),
            jaeger_port=int(os.getenv("JAEGER_PORT", "16686")),
            prometheus_host=os.getenv("PROMETHEUS_HOST", "localhost"),
            prometheus_port=int(os.getenv("PROMETHEUS_PORT", "9090")),
            loki_host=os.getenv("LOKI_HOST", "localhost"),
            loki_port=int(os.getenv("LOKI_PORT", "3100")),
            grafana_host=os.getenv("GRAFANA_HOST", "localhost"),
            grafana_port=int(os.getenv("GRAFANA_PORT", "3000")),
            timeout=int(os.getenv("TIMEOUT", "5")),
        )


# ── Result / Reporter ──────────────────────────────────────────────


class Result:
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class ReportEntry:
    name: str
    status: str  # pass / fail / warn / skip
    detail: str = ""
    latency_ms: float = 0.0


@dataclass
class Reporter:
    entries: list = field(default_factory=list)

    def record(self, name: str, status: str, detail: str = "", latency_ms: float = 0.0):
        self.entries.append(ReportEntry(name=name, status=status, detail=detail, latency_ms=latency_ms))

    def pass_(self, name: str, detail: str = "", latency_ms: float = 0.0):
        self.record(name, Result.PASS, detail, latency_ms)

    def fail(self, name: str, detail: str = "", latency_ms: float = 0.0):
        self.record(name, Result.FAIL, detail, latency_ms)

    def warn(self, name: str, detail: str = "", latency_ms: float = 0.0):
        self.record(name, Result.WARN, detail, latency_ms)

    def skip(self, name: str, detail: str = ""):
        self.record(name, Result.SKIP, detail, 0.0)

    def print_entry(self, entry: ReportEntry):
        if entry.status == Result.PASS:
            prefix = color_pass
        elif entry.status == Result.FAIL:
            prefix = color_fail
        elif entry.status == Result.WARN:
            prefix = color_warn
        else:
            prefix = color_skip

        line = prefix(entry.name)
        if entry.detail:
            line += f"  {DIM}{entry.detail}{RESET}"
        if entry.latency_ms > 0:
            line += f"  {DIM}({entry.latency_ms:.0f}ms){RESET}"
        print(line)

    def print_report(self):
        passed = sum(1 for e in self.entries if e.status == Result.PASS)
        failed = sum(1 for e in self.entries if e.status == Result.FAIL)
        skipped = sum(1 for e in self.entries if e.status == Result.SKIP)
        warned = sum(1 for e in self.entries if e.status == Result.WARN)
        total = len(self.entries)

        color = GREEN if failed == 0 else RED
        print()
        print("=" * 48)
        print(f"  Results: {color}{passed}/{total} passed{RESET}", end="")
        if failed > 0:
            print(f", {RED}{failed} failed{RESET}", end="")
        if warned > 0:
            print(f", {YELLOW}{warned} warned{RESET}", end="")
        if skipped > 0:
            print(f", {skipped} skipped", end="")
        print()
        print("=" * 48)


# ── HTTP helper ────────────────────────────────────────────────────


def http_get(url: str, timeout: int, expect_status: list | None = None, headers: dict | None = None) -> tuple[int, bytes, float]:
    """发起 GET 请求, 返回 (status_code, body_bytes, latency_seconds)."""
    if expect_status is None:
        expect_status = [200]
    if headers is None:
        headers = {}
    req = Request(url, headers=headers)
    start = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            latency = time.perf_counter() - start
            return resp.status, body, latency
    except URLError as exc:
        latency = time.perf_counter() - start
        raise exc from None


def http_get_json(url: str, timeout: int, expect_status: list | None = None) -> tuple[int, object, float]:
    """发起 GET 请求并解析 JSON 响应."""
    status, body, latency = http_get(url, timeout, expect_status)
    data = json.loads(body) if body else None
    return status, data, latency


# ── TCP check ──────────────────────────────────────────────────────


def tcp_check(host: str, port: int, timeout: float) -> float:
    """TCP connect 探测, 成功返回延迟秒数, 失败抛异常."""
    start = time.perf_counter()
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.close()
    return time.perf_counter() - start


def tcp_send_recv(host: str, port: int, send_bytes: bytes, timeout: float) -> tuple[bytes, float]:
    """TCP 连接, 发送数据, 读取响应. 返回 (response_bytes, latency_seconds)."""
    start = time.perf_counter()
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        sock.sendall(send_bytes)
        chunks = []
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                if len(chunk) < 4096:
                    break
            except socket.timeout:
                break
        return b"".join(chunks), time.perf_counter() - start
    finally:
        sock.close()


# ── Checks ─────────────────────────────────────────────────────────


def check_postgres(cfg: Config, rep: Reporter):
    """通过 TCP 连接 + PostgreSQL startup 协议验证 PostgreSQL 可达."""
    label = f"PostgreSQL ({cfg.postgres_host}:{cfg.postgres_port})"
    try:
        lat = tcp_check(cfg.postgres_host, cfg.postgres_port, cfg.timeout)
        # 发送无效的 startup 消息 — PG 会返回 ErrorResponse, 说明确实是 PG 服务
        msg = b"\x00\x00\x00\x08\x04\xd2\x16\x2f"  # length=8, protocol=3.0, no terminator
        try:
            resp, lat2 = tcp_send_recv(cfg.postgres_host, cfg.postgres_port, msg, cfg.timeout)
            # PG 会响应一个 ErrorResponse (type byte 'E') —— 证明这是真正的 PostgreSQL
            if resp and resp[0] == 0x45:  # 'E'
                rep.pass_(label, "TCP OK + PostgreSQL protocol confirmed", lat * 1000)
            else:
                rep.warn(label, f"TCP OK but unexpected response (len={len(resp)})", lat * 1000)
        except Exception as e:
            rep.warn(label, f"TCP OK but protocol check failed: {e}", lat * 1000)
    except Exception as e:
        rep.fail(label, f"cannot connect: {e}")


def check_redis(cfg: Config, rep: Reporter):
    """通过 Redis PING 命令验证 Redis 可达."""
    label = f"Redis ({cfg.redis_host}:{cfg.redis_port})"
    try:
        pong, lat = tcp_send_recv(cfg.redis_host, cfg.redis_port, b"PING\r\n", cfg.timeout)
        pong_str = pong.decode(errors="replace").strip()
        if "PONG" in pong_str:
            rep.pass_(label, f"PING -> {pong_str}", lat * 1000)
        else:
            rep.fail(label, f"unexpected response: {pong_str}", lat * 1000)
    except Exception as e:
        rep.fail(label, f"cannot connect: {e}")


def check_jaeger_api(cfg: Config, rep: Reporter):
    """验证 Jaeger Query API 可用."""
    label = f"Jaeger ({cfg.jaeger_host}:{cfg.jaeger_port})"
    url = f"http://{cfg.jaeger_host}:{cfg.jaeger_port}/api/services"
    try:
        status, data, lat = http_get_json(url, cfg.timeout)
        if status == 200 and isinstance(data, dict) and "data" in data:
            svc_count = len(data.get("data", []))
            rep.pass_(label, f"/api/services OK ({svc_count} services)", lat * 1000)
        else:
            rep.warn(label, f"HTTP {status}, unexpected response shape", lat * 1000)
    except URLError as e:
        rep.fail(label, f"HTTP request failed: {e}")
    except json.JSONDecodeError:
        rep.warn(label, "response is not valid JSON")


def check_prometheus(cfg: Config, rep: Reporter):
    """验证 Prometheus 健康端点."""
    label = f"Prometheus ({cfg.prometheus_host}:{cfg.prometheus_port})"
    url = f"http://{cfg.prometheus_host}:{cfg.prometheus_port}/-/healthy"
    try:
        status, _, lat = http_get(url, cfg.timeout)
        if status == 200:
            rep.pass_(label, "/-/healthy OK", lat * 1000)
        else:
            rep.fail(label, f"HTTP {status}", lat * 1000)
    except URLError as e:
        rep.fail(label, f"cannot connect: {e}")


def check_loki(cfg: Config, rep: Reporter):
    """验证 Loki 就绪端点."""
    label = f"Loki ({cfg.loki_host}:{cfg.loki_port})"
    url = f"http://{cfg.loki_host}:{cfg.loki_port}/ready"
    try:
        status, body, lat = http_get(url, cfg.timeout)
        if status == 200:
            rep.pass_(label, "/ready OK", lat * 1000)
        else:
            rep.fail(label, f"HTTP {status}: {body[:100].decode(errors='replace')}", lat * 1000)
    except URLError as e:
        rep.fail(label, f"cannot connect: {e}")


def check_grafana(cfg: Config, rep: Reporter):
    """验证 Grafana 健康端点."""
    label = f"Grafana ({cfg.grafana_host}:{cfg.grafana_port})"
    url = f"http://{cfg.grafana_host}:{cfg.grafana_port}/api/health"
    try:
        status, body, lat = http_get(url, cfg.timeout)
        if status == 200:
            rep.pass_(label, "/api/health OK", lat * 1000)
        else:
            rep.warn(label, f"HTTP {status}", lat * 1000)
    except URLError as e:
        rep.fail(label, f"cannot connect: {e}")


def check_platform_health(cfg: Config, rep: Reporter):
    """验证 Platform API 健康端点."""
    label = f"Platform API ({cfg.platform_host}:{cfg.platform_port})"
    for path in ["/health", "/api/health"]:
        url = f"http://{cfg.platform_host}:{cfg.platform_port}{path}"
        try:
            status, body, lat = http_get(url, cfg.timeout, expect_status=[200, 404, 401, 403])
            if status == 200:
                rep.pass_(label, f"{path} HTTP {status}", lat * 1000)
                return
            # 404 也说明服务在线, 只是路径不存在
            if status == 404:
                rep.warn(label, f"HTTP 404 on {path}", lat * 1000)
                return
        except URLError:
            continue
    # 尝试根路径
    url = f"http://{cfg.platform_host}:{cfg.platform_port}/"
    try:
        status, _, lat = http_get(url, cfg.timeout, expect_status=range(100, 600))
        if status < 500:
            rep.warn(label, f"root responded HTTP {status} (no dedicated health endpoint found)", lat * 1000)
        else:
            rep.fail(label, f"root HTTP {status}", lat * 1000)
    except URLError as e:
        rep.fail(label, f"cannot connect: {e}")


def check_scheduler_health(cfg: Config, rep: Reporter):
    """验证 Scheduler API 健康端点."""
    label = f"Scheduler API ({cfg.scheduler_host}:{cfg.scheduler_port})"
    for path in ["/health", "/api/health"]:
        url = f"http://{cfg.scheduler_host}:{cfg.scheduler_port}{path}"
        try:
            status, _, lat = http_get(url, cfg.timeout, expect_status=[200, 404, 401, 403])
            if status == 200:
                rep.pass_(label, f"{path} HTTP {status}", lat * 1000)
                return
            if status == 404:
                rep.warn(label, f"HTTP 404 on {path}", lat * 1000)
                return
        except URLError:
            continue
    # 回退: 尝试根路径
    url = f"http://{cfg.scheduler_host}:{cfg.scheduler_port}/"
    try:
        status, _, lat = http_get(url, cfg.timeout, expect_status=range(100, 600))
        if status < 500:
            rep.warn(label, f"root responded HTTP {status} (no health endpoint found)", lat * 1000)
        else:
            rep.fail(label, f"root HTTP {status}", lat * 1000)
    except URLError as e:
        rep.fail(label, f"cannot connect: {e}")


def check_scheduler_endpoints(cfg: Config, rep: Reporter):
    """验证调度中心关键 API 端点."""
    base = f"http://{cfg.scheduler_host}:{cfg.scheduler_port}"
    endpoints = [
        "/api/v1/tasks",
        "/api/v1/agents",
        "/api/v1/queue",
    ]
    for path in endpoints:
        label = f"Scheduler {path}"
        url = f"{base}{path}"
        try:
            status, data, lat = http_get_json(url, cfg.timeout, expect_status=list(range(200, 600)))
            if 200 <= status < 300:
                rep.pass_(label, f"HTTP {status}", lat * 1000)
            elif status == 404:
                rep.skip(label, "endpoint not found")
            elif 400 <= status < 500:
                rep.warn(label, f"HTTP {status} (client error, auth maybe?)", lat * 1000)
            else:
                rep.fail(label, f"HTTP {status}", lat * 1000)
        except URLError as e:
            rep.fail(label, f"{e}")
        except json.JSONDecodeError:
            rep.warn(label, "response is not valid JSON")


def check_platform_endpoints(cfg: Config, rep: Reporter):
    """验证 Platform API 关键端点."""
    base = f"http://{cfg.platform_host}:{cfg.platform_port}"
    endpoints = [
        "/api/v1/workflows",
        "/api/v1/agents",
        "/api/v1/status",
    ]
    for path in endpoints:
        label = f"Platform {path}"
        url = f"{base}{path}"
        try:
            status, data, lat = http_get_json(url, cfg.timeout, expect_status=list(range(200, 600)))
            if 200 <= status < 300:
                rep.pass_(label, f"HTTP {status}", lat * 1000)
            elif status == 404:
                rep.skip(label, "endpoint not found")
            elif 400 <= status < 500:
                rep.warn(label, f"HTTP {status} (client error)", lat * 1000)
            else:
                rep.fail(label, f"HTTP {status}", lat * 1000)
        except URLError as e:
            rep.fail(label, f"{e}")
        except json.JSONDecodeError:
            rep.warn(label, "response is not valid JSON")


def check_jaeger_tracing(cfg: Config, rep: Reporter):
    """验证 Jaeger 中有 trace 数据 (OpenTelemetry 工作正常)."""
    label = "OpenTelemetry Tracing (Jaeger)"
    # 检查 services 列表非空
    url = f"http://{cfg.jaeger_host}:{cfg.jaeger_port}/api/services"
    try:
        status, data, lat = http_get_json(url, cfg.timeout)
        if status == 200 and isinstance(data, dict):
            services = data.get("data", [])
            if services:
                rep.pass_(label, f"{len(services)} service(s) reporting traces", lat * 1000)
            else:
                rep.warn(label, "no services found — wait for traces or check OTEL config", lat * 1000)
        else:
            rep.warn(label, f"HTTP {status}", lat * 1000)
    except URLError as e:
        rep.warn(label, f"Jaeger unreachable: {e}")
    except json.JSONDecodeError:
        rep.warn(label, "Jaeger returned non-JSON response")


def check_prometheus_metrics(cfg: Config, rep: Reporter):
    """验证 Prometheus /metrics 端点返回数据."""
    label = "Prometheus Metrics"
    url = f"http://{cfg.prometheus_host}:{cfg.prometheus_port}/metrics"
    try:
        status, body, lat = http_get(url, cfg.timeout)
        if status == 200 and len(body) > 0:
            line_count = body.count(b"\n")
            rep.pass_(label, f"/metrics OK ({line_count} lines)", lat * 1000)
        elif status == 200:
            rep.warn(label, "/metrics returned empty body", lat * 1000)
        else:
            rep.fail(label, f"HTTP {status}", lat * 1000)
    except URLError as e:
        rep.fail(label, f"cannot connect: {e}")


# ── Main ───────────────────────────────────────────────────────────


def print_banner():
    print()
    print(f"{BOLD}{CYAN}========================================".center(48))
    print(f"  Ado_Jk Platform Smoke Test".center(48))
    print(f"========================================{RESET}")
    print()


def main():
    cfg = Config.from_env()
    rep = Reporter()

    print_banner()

    # ── Infrastructure ──
    print(f"  {BOLD}── Infrastructure Services{RESET}")
    check_postgres(cfg, rep)
    check_redis(cfg, rep)
    check_jaeger_api(cfg, rep)
    check_prometheus(cfg, rep)
    check_loki(cfg, rep)
    check_grafana(cfg, rep)
    print()

    # ── Health Endpoints ──
    print(f"  {BOLD}── Application Health Endpoints{RESET}")
    check_platform_health(cfg, rep)
    check_scheduler_health(cfg, rep)
    print()

    # ── Scheduler API ──
    print(f"  {BOLD}── Scheduler Center Endpoints{RESET}")
    check_scheduler_endpoints(cfg, rep)
    print()

    # ── Platform API ──
    print(f"  {BOLD}── Platform API Endpoints{RESET}")
    check_platform_endpoints(cfg, rep)
    print()

    # ── Observability ──
    print(f"  {BOLD}── Observability{RESET}")
    check_jaeger_tracing(cfg, rep)
    check_prometheus_metrics(cfg, rep)
    print()

    # ── Print entries ──
    for entry in rep.entries:
        rep.print_entry(entry)

    # ── Report ──
    rep.print_report()

    # ── Exit code ──
    has_failure = any(e.status == Result.FAIL for e in rep.entries)
    sys.exit(1 if has_failure else 0)


if __name__ == "__main__":
    main()
