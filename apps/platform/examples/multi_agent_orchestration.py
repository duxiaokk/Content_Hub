#!/usr/bin/env python
"""多 Agent 端到端编排示例

流程: Planner → DataProcessor + ContentGenerator → Auditer → Aggregator

  1. Planner Agent 拆解意图:"分析博客数据，生成一篇技术趋势文章，搜索最新技术资讯并结合"
  2. DataProcessor Agent 处理平台数据，提取关键指标
  3. ToolCalling Agent 搜索最新技术动态
  4. ContentGenerator Agent 根据分析结果&搜索结果撰写文章
  5. Audit Agent 审核文章
  6. Aggregator Agent 聚合最终结果

前置条件:
  1. 调度中心运行:    python -m scheduler_center.main
  2. 所有 Agent 运行: 详见下方启动命令
  3. Redis 运行:      docker compose up -d redis (或本地 Redis)

运行:  python examples/multi_agent_orchestration.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestration_client import OrchestrationClient

client = OrchestrationClient()


# =========================================================================
# 主流程
# =========================================================================


def main() -> None:
    print("=" * 60)
    print("  Multi-Agent Orchestration Demo")
    print("=" * 60)

    # 1. 提交编排意图
    intent = "分析平台博客数据趋势，搜索最新AI技术资讯，生成一篇'2026年AI Agent发展趋势'的博文并审核"
    print(f"\n[1] Submitting intent: {intent[:80]}...")

    try:
        result = client.submit_run(
            intent=intent,
            name="ai-trends-2026",
            context={
                "platform": "Ado_Jk Multi-Agent Platform",
                "blog_posts_count": 25,
            },
        )
    except Exception as e:
        print(f"\n[!] Failed to submit: {e}")
        print("\n   请先启动调度中心和所有 Agent 服务:")
        print("     # 终端1: python -m scheduler_center.main")
        print("     # 终端2: python -m agents.planner_agent")
        print("     # 终端3: python -m agents.data_processor_agent")
        print("     # 终端4: python -m agents.tool_calling_agent")
        print("     # 终端5: python -m agents.content_generator_agent")
        print("     # 终端6: python -m agents.aggregator_agent")
        print("     # 终端7: python audit_agent.py")
        return 1

    run_id = result.get("run_id", "")
    trace_id = result.get("trace_id", "")
    print(f"     Run ID:  {run_id}")
    print(f"     Trace ID: {trace_id}")
    print(f"     Tasks:   {result.get('total_tasks', 0)}")
    print(f"     Status:  {result.get('status', 'unknown')}")

    # 2. 监控运行状态
    print(f"\n[2] Monitoring run {run_id[:8]}...")
    max_wait = 120
    interval = 2
    waited = 0

    while waited < max_wait:
        time.sleep(interval)
        waited += interval
        try:
            status = client.get_run_status(run_id)
        except Exception as e:
            print(f"     [!] Error getting status: {e}")
            continue

        st = status.get("status", "UNKNOWN")
        tasks = status.get("task_statuses", {})
        total = status.get("total_tasks", 0)
        succeeded = status.get("succeeded_tasks", 0)
        failed = status.get("failed_tasks", 0)

        print(f"     [{waited:>3}s] {st:12s} | {succeeded}/{total} done"
              + (f", {failed} failed" if failed else ""))

        if st in ("SUCCEEDED", "FAILED", "PARTIAL", "CANCELED"):
            break

    # 3. 输出结果
    final = client.get_run_status(run_id)
    print(f"\n[3] Final Result")
    print(f"     Status:    {final.get('status')}")
    print(f"     Succeeded: {final.get('succeeded_tasks')}/{final.get('total_tasks')}")

    result_data = final.get("result")
    if result_data:
        summary = result_data.get("summary", "")
        print(f"     Summary:   {summary[:200]}")

    print("\n" + "=" * 60)
    print("  Demo Complete")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
