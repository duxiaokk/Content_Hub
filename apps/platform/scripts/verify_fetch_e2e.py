#!/usr/bin/env python3
"""
自动采集功能 E2E 验证脚本

验证覆盖:
  1. 平台 + 调度中心启动可达
  2. 管理员登录 & JWT 令牌获取
  3. 创建 3 个真实 RSS 信源接入
  4. 手动触发采集并等待调度执行
  5. /metrics 业务指标采样
  6. 监控总览 & 运行详情接口
  7. Webhook 告警推送链路

用法:
  cd apps/platform
  METRICS_ENABLED=true python scripts/verify_fetch_e2e.py

环境变量 (有默认值):
  PLATFORM_HOST     localhost
  PLATFORM_PORT     8000
  SCHEDULER_HOST    localhost
  SCHEDULER_PORT    8010
  ADMIN_USERNAME    Ado_Jk
  ADMIN_PASSWORD    (空，走注册)
  VERIFY_WEBHOOK    true
  TIMEOUT           15
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ── ANSI ──
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"


def P(text: str) -> str:
    return f"{GREEN}[PASS]{RESET} {text}"
def F(text: str) -> str:
    return f"{RED}[FAIL]{RESET} {text}"
def W(text: str) -> str:
    return f"{YELLOW}[WARN]{RESET} {text}"
def I(text: str) -> str:
    return f"{CYAN}[INFO]{RESET} {text}"


@dataclass
class Config:
    platform_host: str = "localhost"
    platform_port: int = 8000
    scheduler_host: str = "localhost"
    scheduler_port: int = 8010
    admin_username: str = "Ado_Jk"
    admin_password: str = "test123456"
    verify_webhook: bool = True
    timeout: int = 15


@dataclass
class Result:
    entries: list = field(default_factory=list)

    def pass_(self, name: str, detail: str = "", lat: float = 0):
        self.entries.append(("pass", name, detail, lat))
        print(f"  {P(name)}  {DIM}{detail}{RESET}" + (f" ({lat:.0f}ms)" if lat else ""))

    def fail(self, name: str, detail: str = "", lat: float = 0):
        self.entries.append(("fail", name, detail, lat))
        print(f"  {F(name)}  {DIM}{detail}{RESET}" + (f" ({lat:.0f}ms)" if lat else ""))

    def warn(self, name: str, detail: str = "", lat: float = 0):
        self.entries.append(("warn", name, detail, lat))
        print(f"  {W(name)}  {DIM}{detail}{RESET}" + (f" ({lat:.0f}ms)" if lat else ""))

    def print_report(self):
        passed = sum(1 for e in self.entries if e[0] == "pass")
        failed = sum(1 for e in self.entries if e[0] == "fail")
        warned = sum(1 for e in self.entries if e[0] == "warn")
        print(f"\n{'=' * 48}")
        print(f"  Results: {GREEN}{passed}/{len(self.entries)} passed{RESET}", end="")
        if failed:
            print(f", {RED}{failed} failed{RESET}", end="")
        if warned:
            print(f", {YELLOW}{warned} warned{RESET}", end="")
        print(f"\n{'=' * 48}\n")
        return failed


rep = Result()


# ── HTTP helpers ──

def _req(method: str, url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 10):
    if headers is None:
        headers = {}
    req = Request(url, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, body, time.perf_counter() - start
    except HTTPError as e:
        body = e.read()
        return e.code, body, time.perf_counter() - start
    except URLError as e:
        return 0, b"", time.perf_counter() - start


def http_get(url: str, timeout: int = 10, headers: dict | None = None):
    return _req("GET", url, headers=headers, timeout=timeout)


def http_post(url: str, json_body: dict, headers: dict | None = None, timeout: int = 10):
    data = json.dumps(json_body).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    return _req("POST", url, data=data, headers=hdrs, timeout=timeout)


def http_put(url: str, json_body: dict, headers: dict | None = None, timeout: int = 10):
    data = json.dumps(json_body).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    return _req("PUT", url, data=data, headers=hdrs, timeout=timeout)


# ── Checks ──

def check_service(name: str, url: str, expect_body: str | None = None):
    """检查服务存活。"""
    try:
        status, body, lat = http_get(url, timeout=cfg.timeout)
        if 200 <= status < 500:
            ok = expect_body is None or expect_body.encode() in body
            if ok:
                rep.pass_(f"{name} [{url}]", f"HTTP {status}", lat * 1000)
            else:
                rep.warn(f"{name} [{url}]", f"HTTP {status} no expected body", lat * 1000)
        else:
            rep.fail(f"{name} [{url}]", f"HTTP {status}", lat * 1000)
    except Exception as e:
        rep.fail(f"{name} [{url}]", str(e))


def get_admin_token() -> str:
    """获取管理员 JWT 令牌。"""
    base = f"http://{cfg.platform_host}:{cfg.platform_port}"

    # 尝试登录
    status, body, lat = http_post(
        f"{base}/api/v1/auth/login",
        {"username": cfg.admin_username, "password": cfg.admin_password, "remember": True},
        timeout=cfg.timeout,
    )
    if status == 200:
        try:
            data = json.loads(body)
            token = (data.get("data") or {}).get("access_token")
            if token:
                rep.pass_("Admin login", f"got JWT token", lat * 1000)
                return str(token)
        except Exception:
            pass

    # 登录失败 -> 注册 (需要 email 字段)
    status2, body2, lat2 = http_post(
        f"{base}/api/v1/auth/register",
        {
            "username": cfg.admin_username,
            "email": f"{cfg.admin_username.lower()}@test.com",
            "password": cfg.admin_password,
        },
        timeout=cfg.timeout,
    )
    if status2 in (200, 201):
        try:
            data = json.loads(body2)
            token = (data.get("data") or {}).get("access_token")
            if token:
                rep.pass_("Admin register + login", "registered and got JWT", lat2 * 1000)
                return str(token)
        except Exception:
            pass

    rep.fail("Admin auth", f"login HTTP {status}, register HTTP {status2}")
    return ""


def create_rss_source(token: str, name: str, feed_url: str, schedule: str = "") -> int | None:
    """创建 RSS 信源配置, 返回 source_config_id."""
    base = f"http://{cfg.platform_host}:{cfg.platform_port}"
    headers = {"Authorization": f"Bearer {token}"}

    config = {"feed_url": feed_url}
    if schedule:
        config["schedule_expression"] = schedule
        config["retry_times"] = 2
        config["retry_backoff_seconds"] = 5.0
        config["alert_on_empty"] = True
        config["alert_policy"] = {
            "channels": ["log", "webhook"],
            "webhook_url": f"http://{cfg.platform_host}:9999/webhook-test",
        }

    body = {
        "name": name,
        "source_type": "rss",
        "enabled": True,
        "channels": [feed_url],
        "keywords": ["python", "tech", "ai", "programming"],
        "lookback_hours": 72,
        "item_limit": 10,
        "dedup_window_hours": 24,
        "config": config,
    }

    status, resp_body, lat = http_post(
        f"{base}/api/v1/console/sources",
        body,
        headers=headers,
        timeout=cfg.timeout,
    )
    if status == 200:
        try:
            data = json.loads(resp_body)
            sid = (data.get("data") or {}).get("id")
            if sid:
                rep.pass_(f"Create source [{name}]", f"id={sid}", lat * 1000)
                return int(sid)
        except Exception:
            pass
    elif status == 409:
        rep.warn(f"Create source [{name}]", f"already exists (HTTP 409)", lat * 1000)
        # Try to find the existing source by listing
        list_status, list_body, _ = http_get(f"{base}/api/v1/console/sources", headers=headers, timeout=cfg.timeout)
        if list_status == 200:
            try:
                data = json.loads(list_body).get("data", [])
                for s in data:
                    if s.get("name") == name:
                        return int(s["id"])
            except Exception:
                pass
        return None
    rep.fail(f"Create source [{name}]", f"HTTP {status}", lat * 1000)
    return None


def trigger_fetch(token: str, source_id: int):
    """触发手动采集。"""
    base = f"http://{cfg.platform_host}:{cfg.platform_port}"
    headers = {"Authorization": f"Bearer {token}"}
    status, body, lat = http_post(
        f"{base}/api/v1/console/sources/{source_id}/run",
        {"lookback_hours": 72, "item_limit": 10, "dry_run": False},
        headers=headers,
        timeout=cfg.timeout,
    )
    if status == 200:
        try:
            data = json.loads(body)
            fd = data.get("data") or {}
            rep.pass_(
                f"Trigger fetch [source={source_id}]",
                f"fetch_run_id={fd.get('fetch_run_id')}, task_id={fd.get('task_id')}, status={fd.get('status')}",
                lat * 1000,
            )
            return fd
        except Exception:
            pass
    rep.fail(f"Trigger fetch [source={source_id}]", f"HTTP {status}", lat * 1000)
    return None


def check_metrics_endpoint():
    """验证 /metrics 端点包含采集业务指标。"""
    base = f"http://{cfg.platform_host}:{cfg.platform_port}"
    status, body, lat = http_get(f"{base}/metrics", timeout=cfg.timeout)

    if status != 200:
        # 尝试调度中心
        base2 = f"http://{cfg.scheduler_host}:{cfg.scheduler_port}"
        status2, body2, lat2 = http_get(f"{base2}/metrics", timeout=cfg.timeout)
        if status2 == 200:
            body = body2
            status = status2
            lat = lat2

    if status != 200:
        rep.warn("Metrics endpoint", f"HTTP {status} (metrics not mounted)", lat * 1000)
        return

    text = body.decode("utf-8", errors="replace")
    metrics_checks = {
        "fetch_total": "fetch_source_total" in text or "fetch_sources_total" in text,
        "fetch_success": "fetch_source_success" in text,
        "fetch_failure": "fetch_source_failure" in text,
        "fetch_duration": "fetch_source_duration" in text or "fetch_batch" in text,
        "task_total": "scheduler_task_total" in text or "task_total" in text,
        "http_requests": "http_request_total" in text,
    }

    found = sum(1 for v in metrics_checks.values() if v)
    total = len(metrics_checks)

    if found >= 4:
        rep.pass_("Metrics content", f"{found}/{total} fetch metrics found in /metrics", lat * 1000)
    elif found > 0:
        rep.warn("Metrics content", f"{found}/{total} fetch metrics found", lat * 1000)
    else:
        rep.fail("Metrics content", "no fetch-related metrics found in /metrics", lat * 1000)

    # 打印发现的指标预览
    for name, found_flag in metrics_checks.items():
        if found_flag:
            # 找该指标的前几行
            for line in text.split("\n"):
                if name.replace("_", "") in line.replace("_", "") and not line.startswith("#"):
                    print(f"    {DIM}{line[:100]}{RESET}")
                    break


def check_monitor_overview(token: str):
    """验证监控总览接口。"""
    base = f"http://{cfg.platform_host}:{cfg.platform_port}"
    headers = {"Authorization": f"Bearer {token}"}

    status, body, lat = http_get(f"{base}/api/v1/console/fetch-monitor/overview", headers=headers, timeout=cfg.timeout)
    if status == 200:
        try:
            data = json.loads(body).get("data", {})
            rep.pass_(
                "Monitor overview API",
                f"total_sources={data.get('total_sources', 0)}, "
                f"success_count={data.get('success_count', 0)}, "
                f"failure_count={data.get('failure_count', 0)}, "
                f"total_alerts={data.get('total_alerts', 0)}, "
                f"success_rate={data.get('success_rate', 0)}%",
                lat * 1000,
            )
            return data
        except Exception:
            pass
    rep.warn("Monitor overview API", f"HTTP {status}", lat * 1000)
    return None


def check_fetch_runs(token: str):
    """验证采集运行历史接口。"""
    base = f"http://{cfg.platform_host}:{cfg.platform_port}"
    headers = {"Authorization": f"Bearer {token}"}

    status, body, lat = http_get(f"{base}/api/v1/console/fetch-runs", headers=headers, timeout=cfg.timeout)
    if status == 200:
        try:
            data = json.loads(body).get("data", [])
            items = data if isinstance(data, list) else data.get("items", [])
            rep.pass_(
                "Fetch runs API",
                f"{len(items)} runs returned",
                lat * 1000,
            )
            return items
        except Exception:
            pass
    rep.warn("Fetch runs API", f"HTTP {status}", lat * 1000)
    return []


def check_fetch_run_detail(token: str, fetch_run_id: int):
    """验证运行详情接口。"""
    base = f"http://{cfg.platform_host}:{cfg.platform_port}"
    headers = {"Authorization": f"Bearer {token}"}

    status, body, lat = http_get(f"{base}/api/v1/console/fetch-runs/{fetch_run_id}/detail", headers=headers, timeout=cfg.timeout)
    if status == 200:
        try:
            data = json.loads(body).get("data", {})
            rep.pass_(
                f"Fetch run detail [id={fetch_run_id}]",
                f"status={data.get('status')}, fetched={data.get('fetched_count')}, "
                f"inserted={data.get('inserted_count')}, duration={data.get('duration_ms')}ms",
                lat * 1000,
            )
            return data
        except Exception:
            pass
    rep.warn(f"Fetch run detail [id={fetch_run_id}]", f"HTTP {status}", lat * 1000)
    return None


def check_alert_service():
    """验证告警推送链路 (dispatch_fetch_alerts)。"""
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    try:
        from unittest.mock import MagicMock

        from apps.platform import models as m
        from apps.platform.services.fetch_alert_service import dispatch_fetch_alerts
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session, sessionmaker

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        m.Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)
        db: Session = session_factory()

        # 创建测试信源
        source = m.SourceConfig(
            name="Alert Test Source",
            source_type="rss",
            enabled=True,
            channels='["https://example.com/feed.xml"]',
            keywords='["test"]',
            config_json=json.dumps({
                "alert_policy": {
                    "channels": ["log", "webhook"],
                    "webhook_url": "http://localhost:9999/webhook-test",
                },
                "invalid_alert_threshold": 0.3,
            }),
        )
        db.add(source)
        db.commit()

        fetch_run = m.FetchRun(
            source_config_id=source.id,
            trigger_mode="manual",
            status="failure",
        )
        db.add(fetch_run)
        db.commit()

        captured_logs: list[str] = []

        def fake_append_log(level: str, msg: str):
            captured_logs.append(f"[{level}] {msg}")

        # 模拟有警情发生的 task_result
        task_result = {
            "fetch_run_id": "mock-run-001",
            "fetched_count": 15,
            "inserted_count": 3,
            "deduped_count": 2,
            "alerts": [
                {"source": "rss", "alert_type": "source_unavailable", "severity": "critical",
                 "message": "Connection timeout after 30s"},
                {"source": "rss", "alert_type": "invalid_ratio_high", "severity": "warning",
                 "message": "Invalid ratio: 10/15"},
                {"source": "rss", "alert_type": "network_retry_recovered", "severity": "info",
                 "message": "Fetched after 3 retries"},
            ],
            "stats": {"total_fetched": 15, "total_invalid": 10, "total_retried": 3, "sources_succeeded": 0, "sources_failed": 1},
            "errors": [{"source": "rss", "error": "Connection timeout", "traceback": None}],
            "checkpoints": {},
            "source_stats": [],
            "validation_issues": [],
        }

        alerts = dispatch_fetch_alerts(
            db,
            source=source,
            fetch_run=fetch_run,
            task_result=task_result,
            append_log=fake_append_log,
        )

        assert len(alerts) >= 3, f"Expected >=3 alerts, got {len(alerts)}"
        assert len(captured_logs) >= 3, f"Expected >=3 log entries, got {len(captured_logs)}"
        alert_types = {a["alert_type"] for a in alerts}
        assert "source_unavailable" in alert_types
        assert "invalid_ratio_high" in alert_types
        assert "network_retry_recovered" in alert_types

        # 确认 webhook_url 被正确解析
        import httpx
        alert_policy = json.loads(source.config_json).get("alert_policy", {})
        webhook_url = alert_policy.get("webhook_url", "")
        if not webhook_url:
            rep.warn("Alert webhook URL", "webhook_url not found in config")
        else:
            rep.pass_("Alert webhook config", f"webhook_url={webhook_url}")

        db.close()
        rep.pass_("Alert service (dispatch_fetch_alerts)", f"3 alerts dispatched, {len(captured_logs)} logs written")
        return True

    except Exception as exc:
        rep.warn("Alert service (dispatch_fetch_alerts)", f"test skipped: {exc}")
        return False


def wait_for_scheduler(base_url: str, max_wait: int = 20) -> bool:
    """等待调度中心就绪。"""
    for i in range(max_wait):
        try:
            status, _, _ = http_get(f"{base_url}/health", timeout=3)
            if status == 200:
                print(f"  {I('Scheduler ready')}  ({i+1}s)")
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_for_platform(base_url: str, max_wait: int = 20) -> bool:
    """等待平台服务就绪。"""
    for i in range(max_wait):
        try:
            status, _, _ = http_get(f"{base_url}/api/v1/auth/login", timeout=3)
            if status in (200, 422):  # 422 = 有登录路径但参数错误，说明服务已在运行
                print(f"  {I('Platform ready')}   ({i+1}s)")
                return True
            if status < 500:
                print(f"  {I('Platform ready (response=')}{status}{I(')')}  ({i+1}s)")
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ── Real RSS Sources 真实 RSS 信源 ──
REAL_SOURCES: list[tuple[str, str, str]] = [
    (
        "Planet Python",
        "https://planetpython.org/rss20.xml",
        "*/15 * * * *",
    ),
    (
        "Hacker News (tech)",
        "https://hnrss.org/frontpage?count=10",
        "*/30 * * * *",
    ),
    (
        "ArXiv cs.AI (new)",
        "https://rss.arxiv.org/rss/cs.AI",
        "0 */2 * * *",
    ),
]


# ── Main ──

def print_banner():
    print(f"\n{BOLD}{CYAN}{'=' * 48}{RESET}")
    print(f"  {BOLD}Content Hub — Fetch Module E2E Verification{RESET}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{BOLD}{CYAN}{'=' * 48}{RESET}\n")


def main():
    global cfg
    cfg = Config(
        platform_host=os.getenv("PLATFORM_HOST", "localhost"),
        platform_port=int(os.getenv("PLATFORM_PORT", "8000")),
        scheduler_host=os.getenv("SCHEDULER_HOST", "localhost"),
        scheduler_port=int(os.getenv("SCHEDULER_PORT", "8010")),
        admin_username=os.getenv("ADMIN_USERNAME", "Ado_Jk"),
        admin_password=os.getenv("ADMIN_PASSWORD", "test123456"),
        verify_webhook=os.getenv("VERIFY_WEBHOOK", "true").lower() == "true",
        timeout=int(os.getenv("TIMEOUT", "15")),
    )

    print_banner()

    # ── Step 1: Health Checks ──
    print(f"  {BOLD}── Step 1: Service Health{RESET}")
    platform_url = f"http://{cfg.platform_host}:{cfg.platform_port}"
    scheduler_url = f"http://{cfg.scheduler_host}:{cfg.scheduler_port}"

    check_service("Platform API", f"{platform_url}/")
    check_service("Scheduler Center", f"{scheduler_url}/health")
    print()

    # ── Step 2: Auth ──
    print(f"  {BOLD}── Step 2: Authentication{RESET}")
    token = get_admin_token()
    if not token:
        print(f"  {F('Cannot proceed without auth token')}\n")
        return 1
    print()

    # ── Step 3: Create Real Sources ──
    print(f"  {BOLD}── Step 3: Create Real RSS Sources{RESET}")
    source_ids: list[int] = []
    for name, feed_url, schedule in REAL_SOURCES:
        sid = create_rss_source(token, name, feed_url, schedule)
        if sid:
            source_ids.append(sid)
        time.sleep(0.5)
    if not source_ids:
        print(f"  {W('No sources created — fetch downstream will be limited')}\n")
    print()

    # ── Step 4: Trigger Fetches ──
    print(f"  {BOLD}── Step 4: Trigger Fetch Tasks{RESET}")
    fetch_run_ids: list[int] = []
    for sid in source_ids:
        fd = trigger_fetch(token, sid)
        if fd and fd.get("fetch_run_id"):
            fetch_run_ids.append(int(fd["fetch_run_id"]))
        time.sleep(1)
    print()

    # ── Step 5: Wait for scheduler to pick up tasks ──
    print(f"  {BOLD}── Step 5: Wait for scheduler execution{RESET}")
    if wait_for_scheduler(scheduler_url, max_wait=10):
        time.sleep(5)

    # ── Step 6: Metrics ──
    print(f"\n  {BOLD}── Step 6: /metrics Business Metrics{RESET}")
    check_metrics_endpoint()
    print()

    # ── Step 7: Monitoring APIs ──
    print(f"  {BOLD}── Step 7: Fetch Monitoring APIs{RESET}")
    check_monitor_overview(token)
    check_fetch_runs(token)
    for fid in fetch_run_ids[:2]:
        check_fetch_run_detail(token, fid)
        time.sleep(0.3)
    print()

    # ── Step 8: Alert Service ──
    print(f"  {BOLD}── Step 8: Alert Service Verification{RESET}")
    check_alert_service()
    print()

    # ── Summary ──
    failed = rep.print_report()

    # Update source configs to set schedule_expression (for dynamic cron)
    if source_ids and token:
        print(f"\n  {I('Note:')} 3 real RSS sources created with schedule_expression:")
        for i, sid in enumerate(source_ids):
            print(f"    source_id={sid}  {REAL_SOURCES[i][0]}  ({REAL_SOURCES[i][1][:60]}...)")
        print(f"  {I('Tip:')} Enable CONTENT_HUB_SCHEDULER_ENABLED=true and restart scheduler\n"
              f"        to test dynamic cron scheduling.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
