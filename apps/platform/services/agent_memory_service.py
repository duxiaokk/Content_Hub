from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

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

    def record_preference(
        self,
        *,
        scope: str,
        scope_key: str | None,
        preference_key: str,
        value: dict[str, Any],
        source: str | None = None,
        expires_at: datetime | None = None,
    ) -> AgentMemory:
        return self.upsert_memory(
            scope=scope,
            scope_key=scope_key,
            memory_type="preference",
            memory_key=preference_key,
            value=value,
            source=source,
            expires_at=expires_at,
        )

    def record_review_feedback(
        self,
        *,
        content_item_id: int,
        decision: str,
        reviewer: str,
        note: str | None = None,
        source_url: str | None = None,
        workflow_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMemory:
        payload = {
            "content_item_id": content_item_id,
            "decision": decision,
            "reviewer": reviewer,
            "note": note,
            "source_url": source_url,
        }
        if workflow_name:
            payload["workflow_name"] = workflow_name
        if metadata:
            payload["metadata"] = metadata
        return self.upsert_memory(
            scope="review",
            scope_key=str(content_item_id),
            memory_type="feedback",
            memory_key=f"review:{content_item_id}",
            value=payload,
            source="review_service",
        )

    def record_workflow_outcome(
        self,
        *,
        workflow_name: str,
        payload: dict[str, Any],
        source: str | None = None,
    ) -> AgentMemory:
        return self.upsert_memory(
            scope="workflow",
            scope_key=workflow_name,
            memory_type="outcome",
            memory_key="last_run",
            value=payload,
            source=source,
        )

    def record_manual_feedback(
        self,
        *,
        scope: str,
        scope_key: str | None,
        feedback_key: str,
        value: dict[str, Any],
        source: str | None = None,
        expires_at: datetime | None = None,
    ) -> AgentMemory:
        return self.upsert_memory(
            scope=scope,
            scope_key=scope_key,
            memory_type="feedback",
            memory_key=feedback_key,
            value=value,
            source=source,
            expires_at=expires_at,
        )

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

    def search_memories(
        self,
        *,
        keyword: str,
        scopes: list[str] | None = None,
        memory_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        normalized_keyword = keyword.strip()
        if not normalized_keyword:
            return []
        with self._session() as db:
            rows = self._search_with_sqlite_fts(
                db,
                keyword=normalized_keyword,
                scopes=scopes,
                memory_type=memory_type,
                limit=limit,
            )
            if not rows:
                rows = self._search_with_token_score(
                    db,
                    keyword=normalized_keyword,
                    scopes=scopes,
                    memory_type=memory_type,
                    limit=limit,
                )
        return rows

    def build_rewrite_preferences(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        memory_context = self.build_planner_context(context)
        merged: dict[str, Any] = {}
        for scope_name in ("global", "user", "workflow"):
            scope_payload = memory_context.get(scope_name)
            if not isinstance(scope_payload, dict):
                continue
            preference_payload = scope_payload.get("preference")
            if not isinstance(preference_payload, dict):
                continue
            for _, value in preference_payload.items():
                if isinstance(value, dict):
                    merged.update(value)
        return merged

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

    def _search_with_sqlite_fts(
        self,
        db: Session,
        *,
        keyword: str,
        scopes: list[str] | None,
        memory_type: str | None,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        bind = db.get_bind()
        if bind is None or bind.dialect.name != "sqlite":
            return None

        match_query = self._build_fts_match_query(keyword)
        if not match_query:
            return []

        try:
            db.execute(text("DROP TABLE IF EXISTS temp.memory_search"))
            db.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE temp.memory_search USING fts5(
                        row_id UNINDEXED,
                        scope,
                        scope_key,
                        memory_type,
                        memory_key,
                        value_text
                    )
                    """
                )
            )

            rows = self.list_memories(limit=max(limit * 10, 100))
            for row in rows:
                if scopes and row.scope not in scopes:
                    continue
                if memory_type and row.memory_type != memory_type:
                    continue
                db.execute(
                    text(
                        """
                        INSERT INTO temp.memory_search
                            (row_id, scope, scope_key, memory_type, memory_key, value_text)
                        VALUES
                            (:row_id, :scope, :scope_key, :memory_type, :memory_key, :value_text)
                        """
                    ),
                    {
                        "row_id": int(row.id),
                        "scope": row.scope,
                        "scope_key": row.scope_key or "",
                        "memory_type": row.memory_type,
                        "memory_key": row.memory_key,
                        "value_text": self._stringify_value(row.value_json),
                    },
                )

            matches = db.execute(
                text(
                    """
                    SELECT
                        agent_memory.id,
                        agent_memory.scope,
                        agent_memory.scope_key,
                        agent_memory.memory_type,
                        agent_memory.memory_key,
                        agent_memory.value_json,
                        agent_memory.source,
                        bm25(memory_search) AS score
                    FROM temp.memory_search AS memory_search
                    JOIN agent_memory ON agent_memory.id = memory_search.row_id
                    WHERE memory_search MATCH :match_query
                    ORDER BY score ASC, agent_memory.updated_at DESC, agent_memory.id DESC
                    LIMIT :limit
                    """
                ),
                {"match_query": match_query, "limit": limit},
            ).mappings()

            return [
                {
                    "scope": str(row["scope"]),
                    "scope_key": row["scope_key"],
                    "memory_type": str(row["memory_type"]),
                    "memory_key": str(row["memory_key"]),
                    "value": self._parse_value(str(row["value_json"])),
                    "source": row["source"],
                    "score": float(row["score"]) if row["score"] is not None else 0.0,
                }
                for row in matches
            ]
        except OperationalError:
            return None

    def _search_with_token_score(
        self,
        db: Session,
        *,
        keyword: str,
        scopes: list[str] | None,
        memory_type: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        tokens = self._tokenize(keyword)
        if not tokens:
            return []

        scored_results: list[tuple[float, AgentMemory]] = []
        rows = self.list_memories(limit=max(limit * 10, 100))
        for row in rows:
            if scopes and row.scope not in scopes:
                continue
            if memory_type and row.memory_type != memory_type:
                continue

            haystack = " ".join(
                [
                    row.scope,
                    row.scope_key or "",
                    row.memory_type,
                    row.memory_key,
                    self._stringify_value(row.value_json),
                ]
            ).lower()
            score = 0.0
            for token in tokens:
                occurrences = haystack.count(token)
                if occurrences:
                    score += occurrences * max(len(token), 1)
            if score <= 0:
                continue
            scored_results.append((score, row))

        scored_results.sort(key=lambda item: (-item[0], -(item[1].id or 0)))
        return [
            {
                "scope": row.scope,
                "scope_key": row.scope_key,
                "memory_type": row.memory_type,
                "memory_key": row.memory_key,
                "value": self._parse_value(row.value_json),
                "source": row.source,
                "score": score,
            }
            for score, row in scored_results[:limit]
        ]

    @staticmethod
    def _build_fts_match_query(keyword: str) -> str:
        tokens = AgentMemoryService._tokenize(keyword)
        if not tokens:
            return ""
        return " OR ".join(f'"{token}"' for token in tokens)

    @staticmethod
    def _tokenize(keyword: str) -> list[str]:
        lowered = keyword.strip().lower()
        if not lowered:
            return []
        latin_tokens = [token for token in re.split(r"[^0-9a-zA-Z_]+", lowered) if token]
        cjk_chars = [char for char in lowered if "\u4e00" <= char <= "\u9fff"]
        cjk_terms: list[str] = []
        if cjk_chars:
            cjk_text = "".join(cjk_chars)
            cjk_terms.append(cjk_text)
            if len(cjk_text) > 1:
                cjk_terms.extend(cjk_text[index : index + 2] for index in range(len(cjk_text) - 1))
        tokens = latin_tokens + cjk_terms + cjk_chars
        deduped: list[str] = []
        for token in tokens:
            if token not in deduped:
                deduped.append(token)
        return deduped

    @staticmethod
    def _stringify_value(raw: str) -> str:
        parsed = AgentMemoryService._parse_value(raw)
        if isinstance(parsed, str):
            return parsed
        return json.dumps(parsed, ensure_ascii=False, default=str)
