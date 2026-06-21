from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from apps.platform.database import SessionLocal
from apps.platform.models import AgentMemory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentMemoryService:
    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    @contextmanager
    def _session(self) -> Generator[Session, None, None]:
        if self._db is not None:
            yield self._db
            return
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def upsert_memory(
        self,
        *,
        scope: str,
        scope_key: str | None,
        memory_type: str,
        memory_key: str,
        value: Any,
        source: str | None = None,
        expires_at: datetime | None = None,
    ) -> AgentMemory:
        with self._session() as db:
            row = (
                db.query(AgentMemory)
                .filter(
                    AgentMemory.scope == scope,
                    AgentMemory.scope_key == scope_key,
                    AgentMemory.memory_key == memory_key,
                )
                .first()
            )
            if row is None:
                row = AgentMemory(
                    scope=scope,
                    scope_key=scope_key,
                    memory_type=memory_type,
                    memory_key=memory_key,
                    value_json="{}",
                )
            row.memory_type = memory_type
            row.value_json = json.dumps(value, ensure_ascii=False, default=str)
            row.source = source
            row.expires_at = expires_at
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

    def list_memories(
        self,
        *,
        scope: str | None = None,
        scope_key: str | None = None,
        memory_types: list[str] | None = None,
        include_global: bool = False,
        limit: int = 100,
    ) -> list[AgentMemory]:
        with self._session() as db:
            try:
                query = db.query(AgentMemory)
                now = _utcnow()
                query = query.filter((AgentMemory.expires_at.is_(None)) | (AgentMemory.expires_at > now))
                if scope is not None:
                    if include_global:
                        query = query.filter(
                            ((AgentMemory.scope == scope) & (AgentMemory.scope_key == scope_key))
                            | (AgentMemory.scope == "global")
                        )
                    else:
                        query = query.filter(AgentMemory.scope == scope, AgentMemory.scope_key == scope_key)
                elif scope_key is not None:
                    query = query.filter(AgentMemory.scope_key == scope_key)
                if memory_types:
                    query = query.filter(AgentMemory.memory_type.in_(memory_types))
                rows = (
                    query.order_by(AgentMemory.updated_at.desc(), AgentMemory.id.desc())
                    .limit(limit)
                    .all()
                )
                return list(rows)
            except OperationalError:
                return []

    def build_planner_context(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = dict(context or {})
        user_scope_key = self._resolve_scope_key(context, ("user_id", "user_key", "username"))
        workflow_scope_key = self._resolve_scope_key(context, ("workflow_name", "workflow_key"))

        payload: dict[str, Any] = {}
        payload["global"] = self._group_rows(
            self.list_memories(scope="global", scope_key=None, memory_types=None, include_global=False)
        )
        if user_scope_key:
            payload["user"] = self._group_rows(
                self.list_memories(scope="user", scope_key=user_scope_key, include_global=False)
            )
        if workflow_scope_key:
            payload["workflow"] = self._group_rows(
                self.list_memories(scope="workflow", scope_key=workflow_scope_key, include_global=False)
            )
        return {key: value for key, value in payload.items() if value}

    def get_memory_value(
        self,
        *,
        scope: str,
        scope_key: str | None,
        memory_type: str,
        memory_key: str,
    ) -> Any:
        rows = self.list_memories(
            scope=scope,
            scope_key=scope_key,
            memory_types=[memory_type],
            include_global=False,
            limit=50,
        )
        for row in rows:
            if row.memory_key == memory_key:
                return self._parse_value(row.value_json)
        return None

    @staticmethod
    def _resolve_scope_key(context: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = context.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _group_rows(rows: list[AgentMemory]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            grouped.setdefault(row.memory_type, {})[row.memory_key] = AgentMemoryService._parse_value(row.value_json)
        return grouped

    @staticmethod
    def _parse_value(raw: str) -> Any:
        try:
            return json.loads(raw or "null")
        except json.JSONDecodeError:
            return raw
