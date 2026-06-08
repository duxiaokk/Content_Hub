"""
功能摘要：本文件提供基于 Redis（远程字典服务）的缓存读写能力，加速热门数据访问。

初学者指南：
这个文件是平台系统的"高速缓存层"。当某些数据查询很慢时，
可以先从这里取结果，避免重复访问数据库。如果缓存服务未配置或连接失败，
函数会静默降级，不影响主业务流程。如果你要新增缓存用途，可以参考 get_json() 和 set_json() 的用法。

主要成员：
- get_json(): 从缓存中读取结构化数据
- set_json(): 将结构化数据写入缓存，可设置过期时间
- delete_prefix(): 按前缀批量删除缓存条目，常用于数据更新后清空旧缓存
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Optional

from core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_redis_client():
    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as exc:  # pragma: no cover - optional dependency/runtime issue
        logger.warning("redis unavailable: %s", exc)
        return None


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - cache must never break requests
        logger.warning("cache operation failed: %s", exc)
        return None


def get_json(key: str) -> Optional[Any]:
    client = get_redis_client()
    if not client:
        return None
    raw = _safe_call(client.get, key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        logger.warning("cache payload decode failed for key=%s", key)
        return None


def set_json(key: str, value: Any, ttl_seconds: int = 300) -> None:
    client = get_redis_client()
    if not client:
        return None
    payload = json.dumps(value, ensure_ascii=False, default=str)
    _safe_call(client.setex, key, ttl_seconds, payload)


def delete(key: str) -> None:
    client = get_redis_client()
    if not client:
        return None
    _safe_call(client.delete, key)


def delete_prefix(prefix: str) -> None:
    client = get_redis_client()
    if not client:
        return None
    keys = _safe_call(client.keys, f"{prefix}*") or []
    if keys:
        _safe_call(client.delete, *keys)
