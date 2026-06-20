from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class AgentMessage:
    """Agent 间通信消息。

    sender:     发送方 agent_key 或 orchestrator
    recipient:  接收方 agent_key 或 orchestrator
    message_type: 消息类型
    payload:    业务负载
    trace_id:   链路追踪 ID
    id:         消息唯一 ID
    status:     当前状态
    created_at: 创建时间
    """

    sender: str
    recipient: str
    message_type: str  # task / result / error / heartbeat / plan
    payload: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"  # pending / delivered / acked / failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "payload": self.payload,
            "trace_id": self.trace_id,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        return cls(
            id=str(data.get("id", uuid.uuid4())),
            sender=str(data["sender"]),
            recipient=str(data["recipient"]),
            message_type=str(data["message_type"]),
            payload=data.get("payload", {}),
            trace_id=data.get("trace_id"),
            status=str(data.get("status", "pending")),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )


@dataclass(slots=True)
class OrchestrationRequest:
    """用户提交给 Orchestrator 的请求。"""

    intent: str
    context: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None


@dataclass(slots=True)
class OrchestrationResult:
    """Orchestrator 返回的最终结果。"""

    trace_id: str
    success: bool
    aggregated_result: dict[str, Any]
    summary: str
    task_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    duration_seconds: float = 0.0
