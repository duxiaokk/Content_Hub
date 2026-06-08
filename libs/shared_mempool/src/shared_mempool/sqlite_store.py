from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class SqliteRecord:
    key: str
    value: bytes
    created_at: int
    updated_at: int
    expires_at: int | None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= int(time.time())


class SqliteStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    @property
    def db_path(self) -> str:
        return self._db_path

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def put(self, namespace: str, key: str, value: bytes, ttl_seconds: int | None) -> None:
        now = int(time.time())
        expires_at = now + int(ttl_seconds) if ttl_seconds is not None else None
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO kv(namespace, key, value, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at
                """,
                (namespace, key, sqlite3.Binary(value), now, now, expires_at),
            )

    def get(self, namespace: str, key: str) -> SqliteRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT key, value, created_at, updated_at, expires_at
                FROM kv
                WHERE namespace=? AND key=?
                """,
                (namespace, key),
            ).fetchone()
            if row is None:
                return None
            record = SqliteRecord(
                key=str(row["key"]),
                value=bytes(row["value"]),
                created_at=int(row["created_at"]),
                updated_at=int(row["updated_at"]),
                expires_at=int(row["expires_at"]) if row["expires_at"] is not None else None,
            )
        if record.is_expired:
            self.delete(namespace, key)
            return None
        return record

    def delete(self, namespace: str, key: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM kv WHERE namespace=? AND key=?", (namespace, key))

    def clear_namespace(self, namespace: str) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM kv WHERE namespace=?", (namespace,))
            return int(cur.rowcount or 0)

    def purge_expired(self, namespace: str | None = None) -> int:
        now = int(time.time())
        with self._lock, self._conn:
            if namespace:
                cur = self._conn.execute(
                    "DELETE FROM kv WHERE namespace=? AND expires_at IS NOT NULL AND expires_at<=?",
                    (namespace, now),
                )
            else:
                cur = self._conn.execute(
                    "DELETE FROM kv WHERE expires_at IS NOT NULL AND expires_at<=?",
                    (now,),
                )
            return int(cur.rowcount or 0)

    def iter_records(self, namespace: str | None = None) -> Iterable[tuple[str, str, bytes, int, int | None]]:
        with self._lock:
            if namespace:
                rows = self._conn.execute(
                    """
                    SELECT namespace, key, value, updated_at, expires_at
                    FROM kv
                    WHERE namespace=?
                    ORDER BY key
                    """,
                    (namespace,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT namespace, key, value, updated_at, expires_at
                    FROM kv
                    ORDER BY namespace, key
                    """
                ).fetchall()
        for row in rows:
            expires_at = int(row["expires_at"]) if row["expires_at"] is not None else None
            if expires_at is not None and expires_at <= int(time.time()):
                continue
            yield (
                str(row["namespace"]),
                str(row["key"]),
                bytes(row["value"]),
                int(row["updated_at"]),
                expires_at,
            )

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv(
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value BLOB NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    expires_at INTEGER NULL,
                    PRIMARY KEY(namespace, key)
                )
                """
            )
