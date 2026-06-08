from __future__ import annotations

import sys
import time
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shared_mempool import MemoryPool, MemoryPoolConfig


class _FakeRedisClient:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._expires_at: dict[str, int] = {}

    def ping(self) -> bool:
        return True

    def get(self, key: str) -> bytes | None:
        exp = self._expires_at.get(key)
        if exp is not None and exp <= int(time.time()):
            self._data.pop(key, None)
            self._expires_at.pop(key, None)
            return None
        return self._data.get(key)

    def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self._data[key] = bytes(value)
        if ex is None:
            self._expires_at.pop(key, None)
        else:
            self._expires_at[key] = int(time.time()) + int(ex)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._expires_at.pop(key, None)

    def ttl(self, key: str) -> int:
        exp = self._expires_at.get(key)
        if exp is None:
            return -1
        return int(exp - int(time.time()))


def _install_fake_redis(fake: _FakeRedisClient) -> None:
    redis_mod = types.ModuleType("redis")

    class Redis:
        @staticmethod
        def from_url(*_args: object, **_kwargs: object) -> _FakeRedisClient:
            return fake

    redis_mod.Redis = Redis
    sys.modules["redis"] = redis_mod


class MemoryPoolTests(unittest.TestCase):
    def test_set_get_hits_redis(self) -> None:
        fake = _FakeRedisClient()
        _install_fake_redis(fake)
        with TemporaryDirectory() as tmp:
            pool = MemoryPool(
                MemoryPoolConfig(
                    namespace="t",
                    sqlite_path=str(Path(tmp) / "db.sqlite"),
                    redis_url="redis://unused",
                    redis_key_prefix="p:",
                    default_ttl_seconds=60,
                    serializer="json",
                )
            )
            try:
                pool.set("k1", {"a": 1}, ttl_seconds=30)
                self.assertEqual(pool.get("k1"), {"a": 1})
                self.assertIsNotNone(fake.get("p:t:k1"))
            finally:
                pool.close()

    def test_get_fallback_to_sqlite_then_warm_redis(self) -> None:
        fake = _FakeRedisClient()
        _install_fake_redis(fake)
        with TemporaryDirectory() as tmp:
            pool = MemoryPool(
                MemoryPoolConfig(
                    namespace="t",
                    sqlite_path=str(Path(tmp) / "db.sqlite"),
                    redis_url="redis://unused",
                    redis_key_prefix="p:",
                    default_ttl_seconds=60,
                    serializer="json",
                )
            )
            try:
                pool.set("k1", {"a": 1}, ttl_seconds=30)
                fake.delete("p:t:k1")
                self.assertIsNone(fake.get("p:t:k1"))
                self.assertEqual(pool.get("k1"), {"a": 1})
                self.assertIsNotNone(fake.get("p:t:k1"))
            finally:
                pool.close()

    def test_ttl_expire(self) -> None:
        fake = _FakeRedisClient()
        _install_fake_redis(fake)
        with TemporaryDirectory() as tmp:
            pool = MemoryPool(
                MemoryPoolConfig(
                    namespace="t",
                    sqlite_path=str(Path(tmp) / "db.sqlite"),
                    redis_url="redis://unused",
                    redis_key_prefix="p:",
                    default_ttl_seconds=60,
                    serializer="json",
                )
            )
            try:
                pool.set("k1", {"a": 1}, ttl_seconds=1)
                self.assertEqual(pool.get("k1"), {"a": 1})
                time.sleep(1.2)
                self.assertIsNone(pool.get("k1"))
            finally:
                pool.close()

    def test_backup_restore(self) -> None:
        fake = _FakeRedisClient()
        _install_fake_redis(fake)
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pool1 = MemoryPool(
                MemoryPoolConfig(
                    namespace="t",
                    sqlite_path=str(tmp_path / "db1.sqlite"),
                    redis_url="redis://unused",
                    redis_key_prefix="p:",
                    default_ttl_seconds=60,
                    serializer="json",
                )
            )
            backup = tmp_path / "backup.jsonl"
            try:
                pool1.set("k1", {"a": 1}, ttl_seconds=60)
                pool1.set("k2", [1, 2, 3], ttl_seconds=None)
                result = pool1.export_jsonl(backup)
                self.assertEqual(result["exported"], 2)
            finally:
                pool1.close()

            pool2 = MemoryPool(
                MemoryPoolConfig(
                    namespace="t",
                    sqlite_path=str(tmp_path / "db2.sqlite"),
                    redis_url="redis://unused",
                    redis_key_prefix="p:",
                    default_ttl_seconds=60,
                    serializer="json",
                )
            )
            try:
                result = pool2.import_jsonl(backup)
                self.assertEqual(result["imported"], 2)
                self.assertEqual(pool2.get("k1"), {"a": 1})
                self.assertEqual(pool2.get("k2"), [1, 2, 3])
            finally:
                pool2.close()


if __name__ == "__main__":
    unittest.main()
