"""可观测性模块

统一初始化入口:
    from core.observability import init_observability

    init_observability("platform", app)  # 初始化日志 + 追踪 + 指标 + 挂载 /metrics
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from core.observability.logging import get_logger
from core.observability.metrics import create_metrics, get_metrics_app
from core.observability.tracing import init_tracing, instrument_app

if TYPE_CHECKING:
    from fastapi import FastAPI


def init_observability(service_name: str, app: "FastAPI | None" = None) -> None:
    """统一初始化可观测性。

    应在 FastAPI app 创建后、uvicorn 启动前调用。

    Args:
        service_name: 服务名 (e.g. "platform", "scheduler-api", "audit-agent")
        app: FastAPI 实例，用于自动埋点和挂载 /metrics
    """
    # 1. 结构化日志
    logger = get_logger(service_name)
    logger.info("Observability initializing", extra={"otel_enabled": os.getenv("OTEL_ENABLED"), "metrics_enabled": os.getenv("METRICS_ENABLED")})

    # 2. OpenTelemetry 追踪
    init_tracing(service_name)
    if app is not None:
        instrument_app(app)

    # 3. Prometheus 指标
    create_metrics(service_name)
    if app is not None and os.getenv("METRICS_ENABLED", "false").lower() == "true":
        try:
            app.mount("/metrics", get_metrics_app())
            logger.info("Mounted /metrics endpoint")
        except Exception as e:
            logger.warning("Failed to mount /metrics", extra={"error": str(e)})

    logger.info("Observability initialized")
