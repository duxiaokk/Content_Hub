"""Agent Registry — 从调度中心发现已注册 Agent。

读取 scheduler_agents 表中的注册信息，为 Orchestrator 提供 Agent 地址和能力查询。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from scheduler_center.models import SchedulerAgent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentInfo:
    """Agent 运行时信息。"""

    agent_key: str
    name: str
    base_url: str
    task_types: list[str]
    capabilities: dict[str, Any]
    health_path: str
    status: int


class AgentRegistry:
    """Agent 注册发现服务。"""

    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    def _session(self) -> Session:
        if self._db is not None:
            return self._db
        from scheduler_center.database import SessionLocal
        return SessionLocal()

    def list_agents(self) -> list[AgentInfo]:
        """列出所有已注册 Agent。"""
        db = self._session()
        try:
            rows = db.query(SchedulerAgent).all()
            return [_map_agent(row) for row in rows if row.status == 1]
        finally:
            if self._db is None:
                db.close()

    def find_agent_by_task_type(self, task_type: str) -> AgentInfo | None:
        """根据 task_type 找到合适的 Agent。"""
        agents = self.list_agents()
        for agent in agents:
            if task_type in agent.task_types:
                return agent
        # 模糊匹配：task_type 前缀匹配
        for agent in agents:
            for tt in agent.task_types:
                if task_type.startswith(tt) or tt.startswith(task_type):
                    return agent
        return None

    def get_agent_url(self, agent_key: str) -> str | None:
        """获取 Agent 的 base_url。"""
        db = self._session()
        try:
            row = db.query(SchedulerAgent).filter(SchedulerAgent.agent_key == agent_key).first()
            return str(row.base_url) if row else None
        finally:
            if self._db is None:
                db.close()

    def get_capability(self, agent_key: str) -> dict[str, Any]:
        """获取 Agent 的能力描述。"""
        db = self._session()
        try:
            row = db.query(SchedulerAgent).filter(SchedulerAgent.agent_key == agent_key).first()
            if not row:
                return {}
            raw = row.capabilities_json
            return json.loads(raw) if raw else {}
        finally:
            if self._db is None:
                db.close()


def _map_agent(row: SchedulerAgent) -> AgentInfo:
    """将 SchedulerAgent ORM 映射为 AgentInfo。"""
    task_types: list[str] = []
    try:
        task_types = json.loads(row.task_types_json or "[]")
    except json.JSONDecodeError:
        pass

    capabilities: dict[str, Any] = {}
    try:
        capabilities = json.loads(row.capabilities_json or "{}")
    except json.JSONDecodeError:
        pass

    return AgentInfo(
        agent_key=str(row.agent_key),
        name=str(row.name),
        base_url=str(row.base_url),
        task_types=task_types,
        capabilities=capabilities,
        health_path=str(row.health_path) if row.health_path else "/health",
        status=int(row.status) if row.status is not None else 1,
    )
