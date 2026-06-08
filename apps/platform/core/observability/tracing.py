"""OpenTelemetry 追踪模块

集成 OpenTelemetry SDK，为以下场景自动/手动埋点:
  - HTTP 请求 (FastAPI 自动)
  - 跨服务 HTTP 调用 (httpx 自动)
  - 数据库查询 (SQLAlchemy 手动)
  - 调度中心任务执行

导出: Jaeger (OTLP gRPC)

环境变量:
  OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
  OTEL_SERVICE_NAME=platform
  OTEL_ENABLED=true

用法:
    from core.observability.tracing import init_tracing, trace, traced

    init_tracing("platform")  # 在 app 启动时调用

    @traced("generate_outline")
    async def my_func(): ...
"""
from __future__ import annotations

import functools
import os
import time
from contextlib import contextmanager
from typing import Any

TRACING_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
_tracer = None
_instrumented = False


def init_tracing(service_name: str) -> None:
    """初始化 OpenTelemetry 追踪。

    应在 FastAPI app 启动前 (uvicorn --preload 之前) 调用。
    """
    global _tracer, _instrumented

    if not TRACING_ENABLED or _instrumented:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        _tracer = trace.get_tracer(service_name)
        _instrumented = True

        # 自动埋点 — 延迟注册 (在有 FastAPI app 时调用)
        import atexit
        atexit.register(provider.shutdown)

    except ImportError:
        pass
    except Exception:
        pass


def instrument_app(app) -> None:
    """对 FastAPI app 进行自动埋点注册。

    在 init_tracing() 之后调用。
    """
    if not TRACING_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument(
            enable_commenter=True,
            commenter_options={"opentelemetry_values": True},
        )
    except ImportError:
        pass
    except Exception:
        pass


def traced(name: str):
    """装饰器: 为函数创建 Span。"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not TRACING_ENABLED or _tracer is None:
                return await func(*args, **kwargs)
            with _tracer.start_as_current_span(name) as span:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(2, str(e))  # ERROR
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not TRACING_ENABLED or _tracer is None:
                return func(*args, **kwargs)
            with _tracer.start_as_current_span(name) as span:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(2, str(e))
                    raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@contextmanager
def trace_block(name: str, **attrs: Any):
    """上下文管理器: 为代码块创建 Span。"""
    if not TRACING_ENABLED or _tracer is None:
        yield
        return

    with _tracer.start_as_current_span(name) as span:
        for k, v in attrs.items():
            span.set_attribute(k, v)
        try:
            yield
        except Exception as e:
            span.record_exception(e)
            span.set_status(2, str(e))
            raise


# ------------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------------

def set_trace_attribute(key: str, value: str | int | float | bool) -> None:
    """在当前 Span 上设置属性。"""
    if not TRACING_ENABLED:
        return
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span:
            span.set_attribute(key, value)
    except Exception:
        pass


def get_current_trace_id() -> str | None:
    """获取当前 trace_id。"""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            return format(span.get_span_context().trace_id, "032x")
    except Exception:
        pass
    return None
