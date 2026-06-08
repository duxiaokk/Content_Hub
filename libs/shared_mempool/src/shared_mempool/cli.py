from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .pool import MemoryPool, MemoryPoolConfig


def _config_from_env() -> MemoryPoolConfig:
    default_ttl: int | None
    raw_ttl = os.getenv("SHARED_MEMPOOL_DEFAULT_TTL_SECONDS", "").strip()
    if raw_ttl == "":
        default_ttl = 3600
    elif raw_ttl.lower() in ("none", "null", "0"):
        default_ttl = None
    else:
        default_ttl = int(raw_ttl)
    return MemoryPoolConfig(
        namespace=os.getenv("SHARED_MEMPOOL_NAMESPACE", "default"),
        default_ttl_seconds=default_ttl,
        serializer=os.getenv("SHARED_MEMPOOL_SERIALIZER", "json"),
        redis_url=os.getenv("SHARED_MEMPOOL_REDIS_URL", "redis://localhost:6379/0"),
        redis_key_prefix=os.getenv("SHARED_MEMPOOL_REDIS_KEY_PREFIX", "shared_mempool:"),
        sqlite_path=os.getenv("SHARED_MEMPOOL_SQLITE_PATH", "./shared_mempool.db"),
    )


def _print_json(data: Any) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(prog="shared-mempool")
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
    pool = MemoryPool(_config_from_env())
    try:
        if args.cmd == "health":
            _print_json(pool.health())
            return 0
        if args.cmd == "get":
            value = pool.get(args.key, namespace=args.namespace)
            _print_json({"key": args.key, "value": value})
            return 0
        if args.cmd == "set":
            value = json.loads(args.value_json)
            pool.set(
                args.key,
                value,
                namespace=args.namespace,
                ttl_seconds=args.ttl,
                persist=bool(args.persist),
            )
            _print_json({"ok": True})
            return 0
        if args.cmd == "delete":
            pool.delete(args.key, namespace=args.namespace)
            _print_json({"ok": True})
            return 0
        if args.cmd == "purge":
            n = pool.purge_expired(namespace=args.namespace)
            _print_json({"purged": n})
            return 0
        if args.cmd == "backup":
            out_path = Path(args.out)
            result = pool.export_jsonl(out_path, namespace=args.namespace)
            _print_json(result)
            return 0
        if args.cmd == "restore":
            in_path = Path(args.in_path)
            result = pool.import_jsonl(in_path, namespace=args.namespace, overwrite=bool(args.overwrite))
            _print_json(result)
            return 0
        raise SystemExit(2)
    finally:
        pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
