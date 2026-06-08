from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
import uuid
from dataclasses import dataclass

import httpx


def _pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int((len(s) - 1) * p)
    return float(s[idx])


@dataclass
class TaskRecord:
    task_id: str
    submit_started_at: float
    submit_finished_at: float
    finished_at: float | None = None
    final_status: str | None = None


async def _submit_one(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    task_type: str,
    idx: int,
    run_id: str,
) -> TaskRecord:
    started = time.perf_counter()
    payload = {
        "task_type": task_type,
        "payload": {
            "comment_id": idx,
            "content": f"load-test-{idx}",
        },
        "max_retries": 2,
        "retry_delay_seconds": 1,
    }
    headers = {
        "x-internal-token": token,
        "x-trace-id": str(uuid.uuid4()),
        "x-idempotency-key": f"load-test:{run_id}:{idx}",
    }
    try:
        resp = await client.post(f"{base_url}/api/internal/scheduler/tasks", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        finished = time.perf_counter()
        return TaskRecord(
            task_id=str(data["id"]),
            submit_started_at=started,
            submit_finished_at=finished,
        )
    except Exception:
        finished = time.perf_counter()
        return TaskRecord(
            task_id="",
            submit_started_at=started,
            submit_finished_at=finished,
            finished_at=finished,
            final_status="SUBMIT_FAILED",
        )


async def _wait_terminal(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    record: TaskRecord,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> TaskRecord:
    if not record.task_id:
        return record
    deadline = time.perf_counter() + timeout_seconds
    headers = {"x-internal-token": token}
    while time.perf_counter() < deadline:
        try:
            resp = await client.get(
                f"{base_url}/api/internal/scheduler/tasks/{record.task_id}",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            status = str(data.get("status") or "")
            if status in {"SUCCEEDED", "FAILED", "CANCELED"}:
                record.final_status = status
                record.finished_at = time.perf_counter()
                return record
        except Exception:
            await asyncio.sleep(poll_interval_seconds)
            continue
        await asyncio.sleep(poll_interval_seconds)
    record.final_status = "TIMEOUT"
    record.finished_at = time.perf_counter()
    return record


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler-url", default=os.getenv("SCHEDULER_URL", "http://127.0.0.1:8010"))
    parser.add_argument(
        "--token",
        default=os.getenv("SCHEDULER_INTERNAL_TOKEN", "local-dev-scheduler-token"),
    )
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("CONCURRENCY", "100")))
    parser.add_argument("--total", type=int, default=int(os.getenv("TOTAL", "200")))
    parser.add_argument("--task-type", default=os.getenv("TASK_TYPE", "comment.moderate"))
    parser.add_argument("--run-id", default=os.getenv("RUN_ID") or uuid.uuid4().hex)
    parser.add_argument("--timeout", type=float, default=float(os.getenv("E2E_TIMEOUT_SECONDS", "60")))
    parser.add_argument("--poll-interval", type=float, default=float(os.getenv("POLL_INTERVAL_SECONDS", "0.05")))
    args = parser.parse_args()

    base_url = str(args.scheduler_url).rstrip("/")
    token = str(args.token)
    run_id = str(args.run_id)

    limits = httpx.Limits(max_connections=max(args.concurrency * 2, 200), max_keepalive_connections=200)
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(limits=limits, timeout=timeout, trust_env=False) as client:
        sem = asyncio.Semaphore(args.concurrency)

        async def submit_wrapped(i: int) -> TaskRecord:
            async with sem:
                return await _submit_one(
                    client,
                    base_url=base_url,
                    token=token,
                    task_type=args.task_type,
                    idx=i,
                    run_id=run_id,
                )

        submit_started = time.perf_counter()
        records = await asyncio.gather(*[submit_wrapped(i) for i in range(args.total)])
        submit_finished = time.perf_counter()

        async def wait_wrapped(r: TaskRecord) -> TaskRecord:
            async with sem:
                return await _wait_terminal(
                    client,
                    base_url=base_url,
                    token=token,
                    record=r,
                    timeout_seconds=args.timeout,
                    poll_interval_seconds=args.poll_interval,
                )

        records = await asyncio.gather(*[wait_wrapped(r) for r in records])

    submit_latencies_ms = [(r.submit_finished_at - r.submit_started_at) * 1000 for r in records]
    e2e_latencies_ms = [(float(r.finished_at or r.submit_finished_at) - r.submit_started_at) * 1000 for r in records]
    succeeded = sum(1 for r in records if r.final_status == "SUCCEEDED")
    failed = sum(1 for r in records if r.final_status in {"FAILED", "SUBMIT_FAILED"})
    timed_out = sum(1 for r in records if r.final_status == "TIMEOUT")

    print("=== load test summary ===")
    print(f"scheduler_url={base_url}")
    print(f"total={args.total} concurrency={args.concurrency}")
    print(f"submit_window_s={(submit_finished - submit_started):.3f}")
    print(f"succeeded={succeeded} failed={failed} timeout={timed_out}")
    print("--- submit latency (ms) ---")
    print(f"p50={_pctl(submit_latencies_ms, 0.50):.2f} p95={_pctl(submit_latencies_ms, 0.95):.2f} max={max(submit_latencies_ms):.2f}")
    print("--- end-to-end latency (ms) ---")
    print(f"p50={_pctl(e2e_latencies_ms, 0.50):.2f} p95={_pctl(e2e_latencies_ms, 0.95):.2f} max={max(e2e_latencies_ms):.2f}")
    print(f"mean={statistics.fmean(e2e_latencies_ms):.2f} stdev={statistics.pstdev(e2e_latencies_ms):.2f}")

    if args.concurrency < 100:
        return 2
    if timed_out > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
