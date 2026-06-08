import os

from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware

from app.api.deps import get_db_session
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import Base, engine
from app.core.mempool import pool as mempool
from app.models.agent import Agent
from app.models.ai_reply import AIReply
from app.models.reply_task import ReplyTask
from app.models.review_queue import ReviewQueue
from app import models  # noqa: F401


Base.metadata.create_all(bind=engine)

def _expected_internal_token() -> str:
    return (
        os.getenv("COMMENT_AGENT_INTERNAL_TOKEN")
        or os.getenv("SCHEDULER_INTERNAL_TOKEN")
        or "local-dev-scheduler-token"
    )


def _maybe_register() -> None:
    scheduler_url = (os.getenv("SCHEDULER_CENTER_URL") or "").strip().rstrip("/")
    base_url = (os.getenv("COMMENT_AGENT_BASE_URL") or "").strip().rstrip("/")
    if not scheduler_url or not base_url:
        return
    payload = {
        "agent_key": os.getenv("COMMENT_AGENT_KEY", "comment-agent"),
        "name": os.getenv("COMMENT_AGENT_NAME", "comment-agent"),
        "base_url": base_url,
        "task_types": ["comment.moderate"],
        "health_path": "/health",
        "capabilities": {"kind": "comment_moderate"},
        "status": 1,
    }
    try:
        httpx.post(
            f"{scheduler_url}/api/internal/scheduler/agents/register",
            json=payload,
            headers={"x-internal-token": _expected_internal_token()},
            timeout=2.0,
        )
    except Exception:
        return


@asynccontextmanager
async def lifespan(_: FastAPI):
    _maybe_register()
    try:
        yield
    finally:
        mempool.close()


app = FastAPI(
    title="Comment Agent",
    version="0.1.0",
    description="Third-party AI comment agent service for blog platforms.",
    lifespan=lifespan,
)
if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready_check() -> dict[str, object]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"db not ready: {exc}",
        ) from exc
    return {"status": "ready", "db_ok": True}


@app.get("/mempool/health")
def mempool_health() -> dict[str, object]:
    return mempool.health()


def _verify_internal_token(request: Request) -> None:
    token = request.headers.get("x-internal-token")
    if not token or token != _expected_internal_token():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


@app.post("/api/internal/agent/run")
def run_internal_agent_task(
    request: Request,
    body: dict,
    db: Session = Depends(get_db_session),
) -> dict:
    _verify_internal_token(request)

    task_type = str(body.get("task_type") or "").strip()
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    if task_type == "comment.moderate":
        comment_id = payload.get("comment_id")
        if comment_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing comment_id")
        content = str(payload.get("content") or "").strip()
        decision = "approved" if content else "rejected"
        mempool.set(
            f"comment-agent:moderate:{int(comment_id)}",
            {
                "task_id": body.get("task_id"),
                "trace_id": body.get("trace_id"),
                "comment_id": int(comment_id),
                "decision": decision,
            },
            ttl_seconds=3600,
        )
        return {
            "ok": True,
            "task_type": task_type,
            "comment_id": int(comment_id),
            "decision": decision,
        }

    reply_task_id = payload.get("reply_task_id")
    if reply_task_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing reply_task_id")

    task = db.query(ReplyTask).filter(ReplyTask.id == int(reply_task_id)).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")

    existing_review = (
        db.query(ReviewQueue)
        .join(AIReply, AIReply.id == ReviewQueue.reply_id)
        .filter(AIReply.task_id == task.id, ReviewQueue.review_status == "pending")
        .first()
    )
    if existing_review is not None:
        return {"ok": True, "status": "already_exists", "task_id": task.id, "review_id": existing_review.id}

    agent = db.query(Agent).filter(Agent.id == task.agent_id).first()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not found")

    reply = AIReply(
        task_id=task.id,
        prompt_snapshot="MVP mock prompt snapshot",
        reply_content="MVP mock AI reply. Replace this with real model output in the worker stage.",
        reply_summary="mock reply",
        moderation_result="pending_review",
        moderation_reason="manual_review_required",
        publish_status="waiting_review",
        model_name=agent.model_name,
    )
    db.add(reply)
    db.flush()

    review = ReviewQueue(
        reply_id=reply.id,
        review_status="pending",
    )
    db.add(review)
    task.task_status = "waiting_review"
    db.commit()
    return {"ok": True, "status": "created", "task_id": task.id, "reply_id": reply.id, "review_id": review.id}
