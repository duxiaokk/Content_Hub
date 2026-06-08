"""统一结构化日志模块

提供 JSON 格式的结构化日志，统一字段：
  service, task_id, trace_id, agent_key, run_id, level

用法:
    from core.observability.logging import get_logger

    logger = get_logger("my-service")
    logger.info("request processed", extra={"task_id": "t1", "trace_id": "tr1"})

支持两种模式:
  - DEV:  彩色控制台输出 (LOG_FORMAT=console)
  - PROD: JSON 输出到 stdout，由 Loki/Promtail 收集 (LOG_FORMAT=json)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextvars import ContextVar
from typing import Any

# Context 变量：跨函数/跨请求传递 trace 信息
_trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)
_task_id_ctx: ContextVar[str | None] = ContextVar("task_id", default=None)
_run_id_ctx: ContextVar[str | None] = ContextVar("run_id", default=None)
_agent_key_ctx: ContextVar[str | None] = ContextVar("agent_key", default=None)


def set_trace_context(
    trace_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    agent_key: str | None = None,
) -> None:
    """设置当前上下文的追踪标识。"""
    if trace_id is not None:
        _trace_id_ctx.set(trace_id)
    if task_id is not None:
        _task_id_ctx.set(task_id)
    if run_id is not None:
        _run_id_ctx.set(run_id)
    if agent_key is not None:
        _agent_key_ctx.set(agent_key)


def clear_trace_context() -> None:
    """清空追踪上下文（请求结束时调用）。"""
    _trace_id_ctx.set(None)
    _task_id_ctx.set(None)
    _run_id_ctx.set(None)
    _agent_key_ctx.set(None)


class JsonFormatter(logging.Formatter):
    """JSON 格式的日志格式化器。"""

    def format(self, record: logging.LogRecord) -> str:
        from datetime import datetime, timezone
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        log_entry: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "service": getattr(record, "service", "unknown"),
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        extras = {
            "trace_id": getattr(record, "trace_id", None) or _trace_id_ctx.get(),
            "task_id": getattr(record, "task_id", None) or _task_id_ctx.get(),
            "run_id": getattr(record, "run_id", None) or _run_id_ctx.get(),
            "agent_key": getattr(record, "agent_key", None) or _agent_key_ctx.get(),
        }
        log_entry.update({k: v for k, v in extras.items() if v is not None})

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class StdoutFilter(logging.Filter):
    """向日志记录注入 service 字段。"""
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service
        return True


def get_logger(service_name: str) -> logging.Logger:
    """获取结构化日志记录器。

    Args:
        service_name: 服务名 (e.g., "platform", "scheduler-api", "audit-agent")
    """
    logger = logging.getLogger(f"app.{service_name}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    log_format = os.getenv("LOG_FORMAT", "json").lower()

    handler = logging.StreamHandler(sys.stdout)
    if log_format == "console":
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(service)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        ))
    else:
        handler.setFormatter(JsonFormatter())

    handler.setLevel(logging.DEBUG)
    handler.addFilter(StdoutFilter(service_name))
    logger.addHandler(handler)

    return logger

def log_event(service: str, event_name: str, **kwargs: Any) -> None:
    """记录业务事件（用于追踪用户行为、任务生命周期等）。"""
    logger = get_logger(service)
    extra = {"event": event_name, **kwargs}
    logger.info(event_name, extra=extra)
