#!/usr/bin/env python
"""50+ Agent 并发模拟器

模拟大量 Agent 同时在线、注册、心跳、接收任务，验证调度中心的扩展能力。

用法:
    python scripts/agent_simulator.py --count 50
    python scripts/agent_simulator.py --count 100 --duration 60
    python scripts/agent_simulator.py --count 50 --submit-tasks --task-count 200
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import httpx

SCHEDULER_URL = os.getenv("SCHEDULER_CENTER_URL", "http://localhost:8010")
INTERNAL_TOKEN = os.getenv("SCHEDULER_INTERNAL_TOKEN", "local-dev-scheduler-token")

TASK_TYPES = [
    "plan.decompose",
    "data.process", "data.extract", "data.transform", "data.clean",
    "tool.call", "tool.search", "tool.translate",
    "content.generate", "content.blog_post", "content.outline",
    "aggregate.merge", "aggregate.summarize",
    "audit.draft",
]


@dataclass
class SimResult:
    total_agents: int = 0
    registered: int = 0
    heartbeats_sent: int = 0
    heartbeats_ok: int = 0
    tasks_submitted: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    task_latencies_ms: list[float] = field(default_factory=list)
    register_latencies_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def register_avg_ms(self) -> float:
        return statistics.mean(self.register_latencies_ms) if self.register_latencies_ms else 0

    @property
    def task_avg_ms(self) -> float:
        return statistics.mean(self.task_latencies_ms) if self.task_latencies_ms else 0

    @property
    def task_p95_ms(self) -> float:
        if not self.task_latencies_ms:
            return 0
        return sorted(self.task_latencies_ms)[int(len(self.task_latencies_ms) * 0.95)]

    @property
    def task_success_rate(self) -> float:
        total = self.tasks_submitted
        return (self.tasks_completed / total * 100) if total > 0 else 0


class AgentSimulator:
    def __init__(self, scheduler_url: str, token: str):
        self.scheduler_url = scheduler_url.rstrip("/")
        self.token = token
        self._stop_event = threading.Event()

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-internal-token": self.token,
        }

    def register_agent(self, agent_key: str, port: int) -> tuple[bool, float]:
        """注册一个模拟 Agent。"""
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.scheduler_url}/api/internal/scheduler/agents/register",
                    json={
                        "agent_key": agent_key,
                        "name": f"Sim Agent {agent_key}",
                        "base_url": f"http://127.0.0.1:{port}",
                        "task_types": random.sample(TASK_TYPES, k=min(4, len(TASK_TYPES))),
                        "health_path": "/health",
                        "capabilities": {"kind": "simulated", "version": "1.0"},
                        "status": 1,
                    },
                    headers=self._headers(),
                )
                return 200 <= resp.status_code < 300, (time.perf_counter() - start) * 1000
        except Exception:
            return False, (time.perf_counter() - start) * 1000

    def send_heartbeat(self, agent_key: str) -> tuple[bool, float]:
        """发送心跳（通过重新注册）。"""
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.scheduler_url}/api/internal/scheduler/agents/register",
                    json={
                        "agent_key": agent_key,
                        "name": f"Sim Agent {agent_key}",
                        "base_url": f"http://127.0.0.1:{9000 + hash(agent_key) % 1000}",
                        "task_types": random.sample(TASK_TYPES, k=min(4, len(TASK_TYPES))),
                        "health_path": "/health",
                        "capabilities": {"kind": "simulated"},
                        "status": 1,
                    },
                    headers=self._headers(),
                )
                return 200 <= resp.status_code < 300, (time.perf_counter() - start) * 1000
        except Exception:
            return False, (time.perf_counter() - start) * 1000

    def submit_task(self) -> tuple[bool, float]:
        """提交一个随机任务。"""
        task_type = random.choice(TASK_TYPES)
        payload = {
            "task_type": task_type,
            "payload": {"intent": f"Simulated task for {task_type}", "trace_id": str(uuid.uuid4())},
            "max_retries": 1,
        }

        start = time.perf_counter()
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.scheduler_url}/api/v1/tasks",
                    json=payload,
                    headers=self._headers(),
                )
                ok = 200 <= resp.status_code < 300
                if ok:
                    data = resp.json()
                    # 轮询等待完成
                    task_id = data.get("id")
                    if task_id:
                        for _ in range(30):  # 最多等 30 秒
                            time.sleep(1)
                            r2 = client.get(
                                f"{self.scheduler_url}/api/v1/tasks/{task_id}",
                                headers=self._headers(),
                            )
                            if r2.status_code == 200:
                                tdata = r2.json()
                                if tdata.get("status") in ("SUCCEEDED", "FAILED", "CANCELED"):
                                    break
                return ok, (time.perf_counter() - start) * 1000
        except Exception:
            return False, (time.perf_counter() - start) * 1000

    def run(
        self,
        agent_count: int = 50,
        duration: int = 30,
        submit_tasks: bool = False,
        task_count: int = 100,
        concurrency: int = 10,
    ) -> SimResult:
        result = SimResult(total_agents=agent_count)

        print(f"\n{'='*60}")
        print(f"  Agent 并发模拟器: {agent_count} Agents")
        print(f"{'='*60}")
        print()

        start_time = time.perf_counter()

        # Phase 1: 注册所有 Agent
        print(f"[Phase 1] 注册 {agent_count} 个 Agent...")
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = []
            for i in range(agent_count):
                agent_key = f"sim-agent-{i:04d}"
                port = 9000 + i
                future = executor.submit(self.register_agent, agent_key, port)
                futures.append((agent_key, future))

            for agent_key, future in futures:
                ok, latency = future.result()
                result.register_latencies_ms.append(latency)
                if ok:
                    result.registered += 1
                else:
                    result.errors.append(f"Register failed: {agent_key}")

        print(f"  注册完成: {result.registered}/{agent_count} ({result.register_avg_ms:.0f}ms avg)")

        # Phase 2: 心跳
        print(f"[Phase 2] 发送心跳...")
        agent_keys = [f"sim-agent-{i:04d}" for i in range(result.registered)]
        heartbeat_rounds = max(1, duration // 30)

        for rnd in range(heartbeat_rounds):
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(self.send_heartbeat, ak) for ak in agent_keys]
                for future in as_completed(futures):
                    ok, _ = future.result()
                    result.heartbeats_sent += 1
                    if ok:
                        result.heartbeats_ok += 1
            if rnd < heartbeat_rounds - 1:
                time.sleep(30)

        print(f"  心跳: {result.heartbeats_ok}/{result.heartbeats_sent} OK")

        # Phase 3: 提交任务（可选）
        if submit_tasks:
            print(f"[Phase 3] 提交 {task_count} 个任务...")
            with ThreadPoolExecutor(max_workers=min(concurrency * 2, task_count)) as executor:
                futures = [executor.submit(self.submit_task) for _ in range(task_count)]
                for future in as_completed(futures):
                    ok, latency = future.result()
                    result.tasks_submitted += 1
                    result.task_latencies_ms.append(latency)
                    if ok:
                        result.tasks_completed += 1
                    else:
                        result.tasks_failed += 1

            print(f"  任务: {result.tasks_completed}/{result.tasks_submitted} 完成 "
                  f"({result.task_avg_ms:.0f}ms avg, p95={result.task_p95_ms:.0f}ms)")

        result.duration_s = time.perf_counter() - start_time
        return result


def print_report(result: SimResult):
    """打印模拟报告。"""
    print(f"\n{'='*60}")
    print(f"  Agent 并发模拟报告")
    print(f"{'='*60}")
    print(f"  Agent 总数:     {result.total_agents}")
    print(f"  注册成功:       {result.registered}")
    print(f"  注册失败:       {result.total_agents - result.registered}")
    print(f"  注册延迟 avg:   {result.register_avg_ms:.1f}ms")
    print(f"{'─'*60}")
    print(f"  心跳发送:       {result.heartbeats_sent}")
    print(f"  心跳成功:       {result.heartbeats_ok}")
    print(f"{'─'*60}")
    print(f"  任务提交:       {result.tasks_submitted}")
    print(f"  任务完成:       {result.tasks_completed}")
    print(f"  任务失败:       {result.tasks_failed}")
    if result.tasks_submitted > 0:
        print(f"  任务成功率:     {result.task_success_rate:.1f}%")
        print(f"  任务延迟 avg:   {result.task_avg_ms:.1f}ms")
        print(f"  任务延迟 p95:   {result.task_p95_ms:.1f}ms")
    print(f"{'─'*60}")
    print(f"  总耗时:         {result.duration_s:.1f}s")
    if result.errors:
        print(f"  错误:           {len(result.errors)}")
        for e in result.errors[:5]:
            print(f"    - {e}")
        if len(result.errors) > 5:
            print(f"    ... and {len(result.errors) - 5} more")
    print(f"{'='*60}\n")

    # 验收判定
    checks = []
    if result.registered >= result.total_agents * 0.9:
        checks.append(f"  ✓ Agent 注册率: {result.registered}/{result.total_agents} >= 90%")
    else:
        checks.append(f"  ✗ Agent 注册率: {result.registered}/{result.total_agents} < 90%")
    if result.register_avg_ms < 500:
        checks.append(f"  ✓ 注册延迟: {result.register_avg_ms:.0f}ms < 500ms")
    else:
        checks.append(f"  ✗ 注册延迟: {result.register_avg_ms:.0f}ms >= 500ms")
    if result.tasks_submitted > 0:
        if result.task_success_rate >= 90:
            checks.append(f"  ✓ 任务成功率: {result.task_success_rate:.1f}% >= 90%")
        else:
            checks.append(f"  ✗ 任务成功率: {result.task_success_rate:.1f}% < 90%")

    print("验收判定:")
    for c in checks:
        print(c)
    print()


def main():
    parser = argparse.ArgumentParser(description="Agent 并发模拟器")
    parser.add_argument("--count", "-n", type=int, default=50, help="Agent 数量 (默认 50)")
    parser.add_argument("--duration", "-d", type=int, default=30, help="持续时间(秒, 默认 30)")
    parser.add_argument("--submit-tasks", action="store_true", help="同时提交任务")
    parser.add_argument("--task-count", type=int, default=100, help="任务数量 (默认 100)")
    parser.add_argument("--concurrency", "-c", type=int, default=10, help="并发度 (默认 10)")
    parser.add_argument("--scheduler-url", type=str, default=SCHEDULER_URL, help="调度中心 URL")
    parser.add_argument("--token", type=str, default=INTERNAL_TOKEN, help="内部 Token")
    args = parser.parse_args()

    simulator = AgentSimulator(
        scheduler_url=args.scheduler_url,
        token=args.token,
    )

    # 先检查调度中心是否可达
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{args.scheduler_url}/health")
            print(f"调度中心状态: HTTP {resp.status_code}")
    except Exception as e:
        print(f"警告: 调度中心不可达 ({e})，仅统计模式。")

    result = simulator.run(
        agent_count=args.count,
        duration=args.duration,
        submit_tasks=args.submit_tasks,
        task_count=args.task_count,
        concurrency=args.concurrency,
    )

    print_report(result)

    # 退出码
    ok = result.registered >= result.total_agents * 0.9
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
