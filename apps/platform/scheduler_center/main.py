from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware

from core.observability import init_observability
from scheduler_center.config import scheduler_settings
from scheduler_center.database import Base, engine
from scheduler_center.dispatcher import SchedulerDispatcher
from scheduler_center.router import router
from scheduler_center.orchestration_router import router as orchestration_router

from apps.platform.multi_agent.orchestrator import Orchestrator
from apps.platform.multi_agent.message_schemas import OrchestrationRequest

dispatcher = SchedulerDispatcher()
_orchestrator = Orchestrator()


def _check_db() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if not scheduler_settings.scheduler_disable_dispatcher:
        dispatcher.start()
    if scheduler_settings.scheduler_cron_enabled:
        dispatcher.start_cron()
    try:
        yield
    finally:
        dispatcher.stop_cron()
        dispatcher.stop()


app = FastAPI(title="Scheduler Center", version="0.1.0", lifespan=lifespan)
if scheduler_settings.scheduler_cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=scheduler_settings.scheduler_cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.include_router(router)
app.include_router(orchestration_router)

# 可观测性初始化
init_observability("scheduler-api", app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, object]:
    try:
        _check_db()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"db not ready: {exc}",
        ) from exc
    return {"status": "ready", "db_ok": True}


# Multi-Agent Orchestrator 入口
@app.post("/api/internal/orchestrate")
async def orchestrate(request: OrchestrationRequest) -> dict[str, object]:
    """用户意图提交到 Multi-Agent Orchestrator。"""
    result = await _orchestrator.execute(intent=request.intent, context=request.context)
    return {
        "trace_id": result.trace_id,
        "success": result.success,
        "summary": result.summary,
        "aggregated_result": result.aggregated_result,
        "task_count": result.task_count,
        "succeeded_count": result.succeeded_count,
        "failed_count": result.failed_count,
        "duration_seconds": result.duration_seconds,
    }

