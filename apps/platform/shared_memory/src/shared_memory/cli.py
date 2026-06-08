from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .pool import SharedMemory, SharedMemoryConfig


def _env(name: str, fallback: str | None = None) -> str:
    v = os.getenv(name, "").strip()
    if v != "":
        return v
    if fallback:
        return os.getenv(fallback, "").strip()
    return ""


def _config_from_env() -> SharedMemoryConfig:
    ns = _env("SHARED_MEMORY_NAMESPACE", "SHARED_MEMPOOL_NAMESPACE") or "default"

    raw_ttl = _env("SHARED_MEMORY_DEFAULT_TTL_SECONDS", "SHARED_MEMPOOL_DEFAULT_TTL_SECONDS")
    if raw_ttl == "":
        default_ttl: int | None = 3600
    elif raw_ttl.lower() in ("none", "null", "0"):
        default_ttl = None
    else:
        default_ttl = int(raw_ttl)

    redis_url = _env("SHARED_MEMORY_REDIS_URL", "SHARED_MEMPOOL_REDIS_URL") or "redis://localhost:6379/0"
    redis_key_prefix = (
        _env("SHARED_MEMORY_REDIS_KEY_PREFIX", "SHARED_MEMPOOL_REDIS_KEY_PREFIX") or "shared_memory:"
    )
    sqlite_path = _env("SHARED_MEMORY_SQLITE_PATH", "SHARED_MEMPOOL_SQLITE_PATH") or "./shared_memory.db"

    redis_timeout = _env("SHARED_MEMORY_REDIS_TIMEOUT_SECONDS", "SHARED_MEMPOOL_REDIS_TIMEOUT_SECONDS")
    redis_connect_timeout = _env(
        "SHARED_MEMORY_REDIS_CONNECT_TIMEOUT_SECONDS",
        "SHARED_MEMPOOL_REDIS_CONNECT_TIMEOUT_SECONDS",
    )
    sqlite_timeout = _env("SHARED_MEMORY_SQLITE_TIMEOUT_SECONDS", "SHARED_MEMPOOL_SQLITE_TIMEOUT_SECONDS")

    return SharedMemoryConfig(
        namespace=ns,
        default_ttl_seconds=default_ttl,
        redis_url=redis_url,
        redis_key_prefix=redis_key_prefix,
        redis_timeout_seconds=float(redis_timeout) if redis_timeout else 2.0,
        redis_connect_timeout_seconds=float(redis_connect_timeout) if redis_connect_timeout else 2.0,
        sqlite_path=sqlite_path,
        sqlite_timeout_seconds=float(sqlite_timeout) if sqlite_timeout else 2.0,
    )


def _print_json(data: Any) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(prog="shared-memory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")

    p_get = sub.add_parser("get")
    p_get.add_argument("key")
    p_get.add_argument("--namespace", default=None)

    p_set = sub.add_parser("set")
    p_set.add_argument("key")
    p_set.add_argument("value_json", help="JSON 字符串（例如：\"123\" / \"{\\\"a\\\":1}\"）")
    p_set.add_argument("--namespace", default=None)
    p_set.add_argument("--ttl", type=int, default=None)
    p_set.add_argument("--persist", action=argparse.BooleanOptionalAction, default=True)

    p_del = sub.add_parser("delete")
    p_del.add_argument("key")
    p_del.add_argument("--namespace", default=None)

    p_purge = sub.add_parser("purge")
    p_purge.add_argument("--namespace", default=None)

    p_backup = sub.add_parser("backup")
    p_backup.add_argument("--out", required=True)
    p_backup.add_argument("--namespace", default=None)

    p_restore = sub.add_parser("restore")
    p_restore.add_argument("--in", dest="in_path", required=True)
    p_restore.add_argument("--namespace", default=None)
    p_restore.add_argument("--overwrite", action=argparse.BooleanOptionalAction, default=True)

    args = parser.parse_args()
    mem = SharedMemory(_config_from_env())
    try:
        if args.cmd == "health":
            _print_json(mem.health())
            return 0
        if args.cmd == "get":
            value = mem.get(args.key, namespace=args.namespace)
            _print_json({"key": args.key, "value": value})
            return 0
        if args.cmd == "set":
            value = json.loads(args.value_json)
            mem.set(
                args.key,
                value,
                namespace=args.namespace,
                ttl_seconds=args.ttl,
                persist=bool(args.persist),
            )
            _print_json({"ok": True})
            return 0
        if args.cmd == "delete":
            mem.delete(args.key, namespace=args.namespace)
            _print_json({"ok": True})
            return 0
        if args.cmd == "purge":
            n = mem.purge_expired(namespace=args.namespace)
            _print_json({"purged": n})
            return 0
        if args.cmd == "backup":
            out_path = Path(args.out)
            result = mem.export_jsonl(out_path, namespace=args.namespace)
            _print_json(result)
            return 0
        if args.cmd == "restore":
            in_path = Path(args.in_path)
            result = mem.import_jsonl(in_path, namespace=args.namespace, overwrite=bool(args.overwrite))
            _print_json(result)
            return 0
        raise SystemExit(2)
    finally:
        mem.close()


if __name__ == "__main__":
    raise SystemExit(main())
