"""Multi-Agent 协作层

为 Content Hub 引入 Multi-Agent 协同工作流：
  - Message Bus: 基于 SQLite 的异步消息队列，解耦 Agent 间通信
  - Agent Registry: 从调度中心发现已注册 Agent 的地址和能力
  - Orchestrator: 任务编排器，负责意图解析 → DAG 分发 → 结果聚合

使用方式:
    from apps.platform.multi_agent import Orchestrator
    orchestrator = Orchestrator()
    result = await orchestrator.execute("抓取 GitHub 并生成摘要")
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保 apps/platform 在 sys.path 中，使 scheduler_center 可作为顶级包导入
_MODULE_DIR = Path(__file__).resolve().parent
_PLATFORM_DIR = _MODULE_DIR.parent
if str(_PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(_PLATFORM_DIR))

from apps.platform.multi_agent.message_bus import MessageBus
from apps.platform.multi_agent.agent_registry import AgentRegistry
from apps.platform.multi_agent.orchestrator import Orchestrator

__all__ = ["MessageBus", "AgentRegistry", "Orchestrator"]
