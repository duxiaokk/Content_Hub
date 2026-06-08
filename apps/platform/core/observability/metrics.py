"""Prometheus 指标模块

统一指标采集，暴露 /metrics 端点。

指标类型:
  - Counter: request_total, task_total, error_total
  - Histogram: request_duration_seconds, task_duration_seconds
  - Gauge: task_queue_depth, agent_online_count, db_connections_active

用法:
    from core.observability.metrics import *

    METRIC_REQUEST_COUNT.labels(service="platform", method="GET", endpoint="/").inc()
    METRIC_REQUEST_DURATION.labels(service="platform", method="GET", endpoint="/").observe(0.15)
    METRIC_TASK_TOTAL.labels(task_type="audit.draft", status="success").inc()
"""
from __future__ import annotations

import os
from typing import Callable

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "false").lower() == "true"

# 延迟导入，避免强依赖
_registry = None
_metrics_created = False

# 全局指标对象（在 create_metrics() 中初始化）
METRIC_REQUEST_COUNT = None
METRIC_REQUEST_DURATION = None
METRIC_TASK_TOTAL = None
METRIC_TASK_DURATION = None
METRIC_TASK_QUEUE_DEPTH = None
METRIC_AGENT_ONLINE_COUNT = None
METRIC_DB_CONNECTIONS_ACTIVE = None
METRIC_RETRY_TOTAL = None
METRIC_ERROR_TOTAL = None
METRIC_LLM_CALL_DURATION = None
METRIC_LLM_CALL_TOTAL = None


def create_metrics(service_name: str | None = None) -> None:
    """创建所有 Prometheus 指标。

    在应用启动时调用一次。
    """
    global _metrics_created
    global METRIC_REQUEST_COUNT, METRIC_REQUEST_DURATION
    global METRIC_TASK_TOTAL, METRIC_TASK_DURATION
    global METRIC_TASK_QUEUE_DEPTH, METRIC_AGENT_ONLINE_COUNT
    global METRIC_DB_CONNECTIONS_ACTIVE, METRIC_RETRY_TOTAL
    global METRIC_ERROR_TOTAL, METRIC_LLM_CALL_DURATION, METRIC_LLM_CALL_TOTAL

    if not METRICS_ENABLED or _metrics_created:
        return

    try:
        from prometheus_client import Counter, Gauge, Histogram, REGISTRY
        global _registry
        _registry = REGISTRY

        labels = {"service": service_name or "unknown"}

        METRIC_REQUEST_COUNT = Counter(
            "http_request_total", "Total HTTP requests",
            ["service", "method", "endpoint", "status_code"],
        )
        METRIC_REQUEST_DURATION = Histogram(
            "http_request_duration_seconds", "HTTP request duration",
            ["service", "method", "endpoint"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
        METRIC_TASK_TOTAL = Counter(
            "task_total", "Total tasks processed",
            ["service", "task_type", "status"],
        )
        METRIC_TASK_DURATION = Histogram(
            "task_duration_seconds", "Task execution duration",
            ["service", "task_type"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
        )
        METRIC_TASK_QUEUE_DEPTH = Gauge(
            "task_queue_depth", "Current task queue depth",
            ["service"],
        )
        METRIC_AGENT_ONLINE_COUNT = Gauge(
            "agent_online_count", "Number of online agents",
            ["service"],
        )
        METRIC_DB_CONNECTIONS_ACTIVE = Gauge(
            "db_connections_active", "Active database connections",
            ["service"],
        )
        METRIC_RETRY_TOTAL = Counter(
            "retry_total", "Total retry attempts",
            ["service", "task_type"],
        )
        METRIC_ERROR_TOTAL = Counter(
            "error_total", "Total errors",
            ["service", "error_type"],
        )
        METRIC_LLM_CALL_DURATION = Histogram(
            "llm_call_duration_seconds", "LLM API call duration",
            ["service", "model"],
            buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
        )
        METRIC_LLM_CALL_TOTAL = Counter(
            "llm_call_total", "Total LLM API calls",
            ["service", "model", "status"],
        )
        _metrics_created = True

    except ImportError:
        pass


def get_metrics_app():
    """返回包含 /metrics 端点的 ASGI app。

    用法:  app.mount("/metrics", get_metrics_app())
    """
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def metrics_endpoint(request):
        try:
            from prometheus_client import generate_latest, REGISTRY
            data = generate_latest(_registry or REGISTRY)
            return PlainTextResponse(data.decode("utf-8"), media_type="text/plain")
        except ImportError:
            return PlainTextResponse("# Prometheus not installed", media_type="text/plain")

    return Starlette(routes=[Route("/", metrics_endpoint)])


# ------------------------------------------------------------------
# 装饰器
# ------------------------------------------------------------------

def track_task_duration(task_type: str):
    """装饰器: 追踪任务执行时长。"""
    def decorator(func: Callable) -> Callable:
        async def async_wrapper(*args, **kwargs):
            import time
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                METRIC_TASK_TOTAL and METRIC_TASK_TOTAL.labels(
                    service=os.getenv("OTEL_SERVICE_NAME", ""), task_type=task_type, status="success",
                ).inc()
                return result
            except Exception:
                METRIC_TASK_TOTAL and METRIC_TASK_TOTAL.labels(
                    service=os.getenv("OTEL_SERVICE_NAME", ""), task_type=task_type, status="failure",
                ).inc()
                raise
            finally:
                METRIC_TASK_DURATION and METRIC_TASK_DURATION.labels(
                    service=os.getenv("OTEL_SERVICE_NAME", ""), task_type=task_type,
                ).observe(time.time() - start)
        return async_wrapper
    return decorator
