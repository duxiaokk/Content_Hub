from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Generator

from apps.platform.multi_agent.message_schemas import AgentMessage

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageBus:
    """基于 SQLite 的异步消息队列。

    - enqueue: 发送消息
    - dequeue: 接收消息（并标记为 delivered）
    - ack:     确认消息已处理
    - get_messages: 按 trace_id 查询消息链
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            base = Path(__file__).resolve().parents[3]  # apps/platform
            db_path = str(base / "multi_agent_messages.db")
        self._db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS agent_messages (
            id TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            message_type TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            trace_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            expires_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_messages_recipient_status
            ON agent_messages(recipient, status);
        CREATE INDEX IF NOT EXISTS idx_messages_trace_id
            ON agent_messages(trace_id);
        CREATE INDEX IF NOT EXISTS idx_messages_created_at
            ON agent_messages(created_at);
        """
        with self._conn() as conn:
            conn.executescript(ddl)
            conn.commit()

    # ------------------------------------------------------------------
    # 核心操作
    # ------------------------------------------------------------------

    def enqueue(self, msg: AgentMessage) -> str:
        """发送消息，返回 message_id。"""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO agent_messages
                (id, sender, recipient, message_type, payload, trace_id, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg.id,
                    msg.sender,
                    msg.recipient,
                    msg.message_type,
                    json.dumps(msg.payload, ensure_ascii=False, default=str),
                    msg.trace_id,
                    msg.status,
                    msg.created_at,
                    None,
                ),
            )
            conn.commit()
        logger.info("MessageBus enqueue: id=%s type=%s sender=%s -> recipient=%s",
                    msg.id, msg.message_type, msg.sender, msg.recipient)
        return msg.id

    def dequeue(self, recipient: str, limit: int = 1) -> list[AgentMessage]:
        """接收消息（标记为 delivered），返回消息列表。"""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, sender, recipient, message_type, payload, trace_id, status, created_at
                FROM agent_messages
                WHERE recipient = ? AND status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (recipient, limit),
            ).fetchall()

            if not rows:
                return []

            messages = []
            for row in rows:
                msg = AgentMessage(
                    id=str(row["id"]),
                    sender=str(row["sender"]),
                    recipient=str(row["recipient"]),
                    message_type=str(row["message_type"]),
                    payload=json.loads(row["payload"] or "{}"),
                    trace_id=row["trace_id"],
                    status="delivered",
                    created_at=str(row["created_at"]),
                )
                conn.execute(
                    "UPDATE agent_messages SET status = 'delivered' WHERE id = ?",
                    (msg.id,),
                )
                messages.append(msg)

            conn.commit()
            return messages

    def ack(self, message_id: str) -> bool:
        """确认消息已处理。"""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE agent_messages SET status = 'acked' WHERE id = ?",
                (message_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def fail(self, message_id: str) -> bool:
        """标记消息处理失败。"""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE agent_messages SET status = 'failed' WHERE id = ?",
                (message_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_messages(self, trace_id: str) -> list[AgentMessage]:
        """按 trace_id 查询所有消息。"""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, sender, recipient, message_type, payload, trace_id, status, created_at
                FROM agent_messages
                WHERE trace_id = ?
                ORDER BY created_at ASC
                """,
                (trace_id,),
            ).fetchall()

        return [
            AgentMessage(
                id=str(r["id"]),
                sender=str(r["sender"]),
                recipient=str(r["recipient"]),
                message_type=str(r["message_type"]),
                payload=json.loads(r["payload"] or "{}"),
                trace_id=r["trace_id"],
                status=str(r["status"]),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]

    def count_pending(self, recipient: str) -> int:
        """查询某 recipient 的 pending 消息数。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM agent_messages WHERE recipient = ? AND status = 'pending'",
                (recipient,),
            ).fetchone()
            return row[0] if row else 0

    def cleanup(self, max_age_hours: int = 24) -> int:
        """清理过期消息，返回删除数量。"""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM agent_messages WHERE created_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cur.rowcount
