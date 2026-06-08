from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass

import httpx


@dataclass
class Proc:
    name: str
    popen: subprocess.Popen[object]

    def stop(self) -> None:
        try:
            self.popen.terminate()
        except Exception:
            pass
        try:
            self.popen.wait(timeout=5)
        except Exception:
            try:
                self.popen.kill()
            except Exception:
                pass


def _wait_http_ready(url: str, *, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    last_err: Exception | None = None
    client = httpx.Client(timeout=httpx.Timeout(1.0), trust_env=False)
    while time.time() < deadline:
        try:
            r = client.get(url)
            if 200 <= r.status_code < 300:
                client.close()
                return
        except Exception as exc:
            last_err = exc
        time.sleep(0.2)
    client.close()
    raise RuntimeError(f"service not ready: {url} err={last_err}")


def _register_agent(
    client: httpx.Client,
    *,
    scheduler_url: str,
    token: str,
    agent_key: str,
    base_url: str,
    health_path: str = "/health",
    task_types: list[str] | None = None,
) -> None:
    payload = {
        "agent_key": agent_key,
        "name": agent_key,
        "base_url": base_url,
        "task_types": task_types or ["*"],
        "health_path": health_path,
        "capabilities": {},
        "status": 1,
    }
    r = client.post(
        f"{scheduler_url}/api/internal/scheduler/agents/register",
        json=payload,
        headers={"x-internal-token": token},
    )
    r.raise_for_status()


def _submit_task(
    client: httpx.Client,
    *,
    scheduler_url: str,
    token: str,
    task_type: str,
    max_retries: int,
    retry_delay: float,
) -> str:
    payload = {
        "task_type": task_type,
        "payload": {"comment_id": 1, "content": "fault-drill"},
        "max_retries": max_retries,
        "retry_delay_seconds": retry_delay,
    }
    headers = {
        "x-internal-token": token,
        "x-trace-id": str(uuid.uuid4()),
        "x-idempotency-key": f"fault-drill-{uuid.uuid4()}",
    }
    r = client.post(f"{scheduler_url}/api/internal/scheduler/tasks", json=payload, headers=headers)
    r.raise_for_status()
    return str(r.json()["id"])


def _wait_task_terminal(
    client: httpx.Client,
    *,
    scheduler_url: str,
    token: str,
    task_id: str,
    timeout_seconds: float = 30.0,
) -> dict:
    deadline = time.time() + timeout_seconds
    headers = {"x-internal-token": token}
    last = None
    while time.time() < deadline:
        r = client.get(f"{scheduler_url}/api/internal/scheduler/tasks/{task_id}", headers=headers)
        r.raise_for_status()
        last = r.json()
        status = str(last.get("status") or "")
        if status in {"SUCCEEDED", "FAILED", "CANCELED"}:
            return last
        time.sleep(0.2)
    raise RuntimeError(f"task not finished in time: {task_id} last={last}")


def _drill_agent_down(client: httpx.Client, *, scheduler_url: str, token: str) -> None:
    _register_agent(
        client,
        scheduler_url=scheduler_url,
        token=token,
        agent_key="drill-agent-down",
        base_url="http://127.0.0.1:65530",
        task_types=["drill.agent_down"],
    )
    task_id = _submit_task(
        client,
        scheduler_url=scheduler_url,
        token=token,
        task_type="drill.agent_down",
        max_retries=2,
        retry_delay=0.5,
    )
    detail = _wait_task_terminal(client, scheduler_url=scheduler_url, token=token, task_id=task_id, timeout_seconds=30)
    attempt_count = int(detail.get("attempt_count") or 0)
    status = str(detail.get("status") or "")
    if status != "FAILED" or attempt_count < 2:
        raise RuntimeError(f"agent-down drill failed: status={status} attempt_count={attempt_count}")
    print(f"[PASS] agent-down: task={task_id} attempt_count={attempt_count} last_error={detail.get('last_error')}")


def _start_agent_stub(*, port: int, delay_seconds: float) -> Proc:
    cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env = os.environ.copy()
    env["AGENT_STUB_DELAY_SECONDS"] = str(delay_seconds)
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "scheduler_center.agent_stub:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    popen = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc = Proc(name="agent-stub", popen=popen)
    _wait_http_ready(f"http://127.0.0.1:{port}/health", timeout_seconds=10)
    return proc


def _drill_network_timeout(client: httpx.Client, *, scheduler_url: str, token: str, delay_seconds: float) -> None:
    proc = _start_agent_stub(port=8021, delay_seconds=delay_seconds)
    try:
        _register_agent(
            client,
            scheduler_url=scheduler_url,
            token=token,
            agent_key="drill-agent-timeout",
            base_url="http://127.0.0.1:8021",
            task_types=["drill.network_timeout"],
        )
        task_id = _submit_task(
            client,
            scheduler_url=scheduler_url,
            token=token,
            task_type="drill.network_timeout",
            max_retries=2,
            retry_delay=0.5,
        )
        detail = _wait_task_terminal(client, scheduler_url=scheduler_url, token=token, task_id=task_id, timeout_seconds=90)
        attempt_count = int(detail.get("attempt_count") or 0)
        status = str(detail.get("status") or "")
        if status != "FAILED" or attempt_count < 2:
            raise RuntimeError(f"network-timeout drill failed: status={status} attempt_count={attempt_count}")
        print(
            f"[PASS] network-timeout: task={task_id} attempt_count={attempt_count} last_error={detail.get('last_error')}"
        )
    finally:
        proc.stop()


def _start_comment_agent_with_bad_redis(*, port: int, token: str) -> Proc:
    cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "Comment_Agent"))
    env = os.environ.copy()
    env["COMMENT_AGENT_INTERNAL_TOKEN"] = token
    env["DATABASE_URL"] = "sqlite:///./comment_agent_fault.db"
    env["MEMPOOL_SQLITE_PATH"] = "./shared_mempool_fault.db"
    env["MEMPOOL_REDIS_URL"] = "redis://127.0.0.1:6390/0"
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    popen = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc = Proc(name="comment-agent-bad-redis", popen=popen)
    _wait_http_ready(f"http://127.0.0.1:{port}/health", timeout_seconds=15)
    return proc


def _drill_redis_unavailable(*, token: str) -> None:
    proc = _start_comment_agent_with_bad_redis(port=8022, token=token)
    try:
        with httpx.Client(timeout=httpx.Timeout(3.0), trust_env=False) as client:
            h = client.get("http://127.0.0.1:8022/mempool/health")
            h.raise_for_status()
            data = h.json()
        if bool(data.get("redis_ok")) is True:
            raise RuntimeError(f"expected redis_ok=false, got: {data}")

        payload = {
            "task_id": "redis-drill",
            "task_type": "comment.moderate",
            "payload": {"comment_id": 1, "content": "redis-down"},
            "attempt_no": 1,
            "trace_id": str(uuid.uuid4()),
        }
        with httpx.Client(timeout=httpx.Timeout(5.0), trust_env=False) as client:
            r = client.post(
                "http://127.0.0.1:8022/api/internal/agent/run",
                json=payload,
                headers={"x-internal-token": token},
            )
            r.raise_for_status()
            print(
                f"[PASS] redis-unavailable: mempool.redis_ok={data.get('redis_ok')} agent_run_ok={r.json().get('ok')}"
            )
    finally:
        proc.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler-url", default=os.getenv("SCHEDULER_URL", "http://127.0.0.1:8010"))
    parser.add_argument("--token", default=os.getenv("SCHEDULER_INTERNAL_TOKEN", "local-dev-scheduler-token"))
    parser.add_argument("--stub-delay", type=float, default=float(os.getenv("AGENT_STUB_DELAY_SECONDS", "20")))
    args = parser.parse_args()

    scheduler_url = str(args.scheduler_url).rstrip("/")
    token = str(args.token)

    _wait_http_ready(f"{scheduler_url}/ready", timeout_seconds=10)

    with httpx.Client(timeout=httpx.Timeout(5.0), trust_env=False) as client:
        _drill_agent_down(client, scheduler_url=scheduler_url, token=token)
        _drill_network_timeout(client, scheduler_url=scheduler_url, token=token, delay_seconds=float(args.stub_delay))

    _drill_redis_unavailable(token=token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
