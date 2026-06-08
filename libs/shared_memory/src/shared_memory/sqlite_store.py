from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class SqliteRecord:
    namespace: str
    key: str
    value: bytes
    created_at: int
    updated_at: int
    expires_at: int | None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= int(time.time())


class SqliteStore:
    def __init__(self, db_path: str | Path, *, timeout_seconds: float = 2.0) -> None:
        self._db_path = str(db_path)
        self._timeout_seconds = float(timeout_seconds)
        self._init_lock = threading.RLock()
        self._local = threading.local()
        self._conns_lock = threading.Lock()
        self._conns: set[sqlite3.Connection] = set()
        self._init_schema()

    @property
    def db_path(self) -> str:
        return self._db_path

    def close(self) -> None:
        with self._conns_lock:
            conns = list(self._conns)
            self._conns.clear()
        for conn in conns:
            try:
                conn.close()
            except Exception:
                pass

    def _new_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            timeout=self._timeout_seconds,
        )
        conn.row_factory = sqlite3.Row
        busy_timeout_ms = int(max(0.0, self._timeout_seconds) * 1000)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        conn = self._new_conn()
        self._local.conn = conn
        with self._conns_lock:
            self._conns.add(conn)
        return conn

    def put(self, namespace: str, key: str, value: bytes, ttl_seconds: int | None) -> None:
        now = int(time.time())
        expires_at = now + int(ttl_seconds) if ttl_seconds is not None else None
        conn = self._get_conn()
        with conn:
            conn.execute(
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
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT namespace, key, value, created_at, updated_at, expires_at
            FROM kv
            WHERE namespace=? AND key=?
            """,
            (namespace, key),
        ).fetchone()
        if row is None:
            return None
        record = SqliteRecord(
            namespace=str(row["namespace"]),
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
        conn = self._get_conn()
        with conn:
            conn.execute("DELETE FROM kv WHERE namespace=? AND key=?", (namespace, key))

    def purge_expired(self, namespace: str | None = None) -> int:
        now = int(time.time())
        conn = self._get_conn()
        with conn:
            if namespace:
                cur = conn.execute(
                    "DELETE FROM kv WHERE namespace=? AND expires_at IS NOT NULL AND expires_at<=?",
                    (namespace, now),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM kv WHERE expires_at IS NOT NULL AND expires_at<=?",
                    (now,),
                )
            return int(cur.rowcount or 0)

    def iter_records(self, namespace: str | None = None) -> Iterable[SqliteRecord]:
        conn = self._get_conn()
        if namespace:
            rows = conn.execute(
                """
                SELECT namespace, key, value, created_at, updated_at, expires_at
                FROM kv
                WHERE namespace=?
                ORDER BY key
                """,
                (namespace,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT namespace, key, value, created_at, updated_at, expires_at
                FROM kv
                ORDER BY namespace, key
                """
            ).fetchall()
        for row in rows:
            record = SqliteRecord(
                namespace=str(row["namespace"]),
                key=str(row["key"]),
                value=bytes(row["value"]),
                created_at=int(row["created_at"]),
                updated_at=int(row["updated_at"]),
                expires_at=int(row["expires_at"]) if row["expires_at"] is not None else None,
            )
            if record.is_expired:
                continue
            yield record

    def acquire_lock(
        self,
        namespace: str,
        key: str,
        owner: str,
        *,
        ttl_seconds: int,
        timeout_seconds: float,
    ) -> None:
        deadline = time.monotonic() + float(timeout_seconds)
        ttl = max(1, int(ttl_seconds))
        conn = self._get_conn()
        while True:
            now = int(time.time())
            expires_at = now + ttl
            with conn:
                conn.execute("DELETE FROM locks WHERE expires_at<=?", (now,))
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO locks(namespace, key, owner, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (namespace, key, owner, now, expires_at),
                )
                if int(cur.rowcount or 0) > 0:
                    return
                row = conn.execute(
                    "SELECT owner FROM locks WHERE namespace=? AND key=?",
                    (namespace, key),
                ).fetchone()
                if row is not None and str(row["owner"]) == owner:
                    conn.execute(
                        "UPDATE locks SET expires_at=? WHERE namespace=? AND key=? AND owner=?",
                        (expires_at, namespace, key, owner),
                    )
                    return
            if time.monotonic() >= deadline:
                raise TimeoutError("lock timeout")
            time.sleep(0.05)

    def release_lock(self, namespace: str, key: str, owner: str) -> bool:
        conn = self._get_conn()
        with conn:
            cur = conn.execute(
                "DELETE FROM locks WHERE namespace=? AND key=? AND owner=?",
                (namespace, key, owner),
            )
            return int(cur.rowcount or 0) > 0

    def _init_schema(self) -> None:
        with self._init_lock:
            conn = self._new_conn()
            with conn:
                conn.execute(
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
                conn.execute(
                """
                CREATE TABLE IF NOT EXISTS locks(
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY(namespace, key)
                )
                """
            )
            conn.close()
