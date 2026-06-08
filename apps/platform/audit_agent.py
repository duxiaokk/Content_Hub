from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, status

from core.mempool import get_pool
from core.observability import init_observability
from services.llm_client import get_default_provider


def _expected_token() -> str:
    return (
        os.getenv("AUDIT_AGENT_INTERNAL_TOKEN")
        or os.getenv("SCHEDULER_INTERNAL_TOKEN")
        or "local-dev-scheduler-token"
    )


def _verify_internal_token(request: Request) -> None:
    token = request.headers.get("x-internal-token")
    if not token or token != _expected_token():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def _maybe_register() -> None:
    scheduler_url = (os.getenv("SCHEDULER_CENTER_URL") or "").strip().rstrip("/")
    base_url = (os.getenv("AUDIT_AGENT_BASE_URL") or "").strip().rstrip("/")
    if not scheduler_url or not base_url:
        return
    payload = {
        "agent_key": os.getenv("AUDIT_AGENT_KEY", "audit-agent"),
        "name": os.getenv("AUDIT_AGENT_NAME", "audit-agent"),
        "base_url": base_url,
        "task_types": ["audit.draft"],
        "health_path": "/health",
        "capabilities": {"kind": "draft_audit"},
        "status": 1,
    }
    try:
        httpx.post(
            f"{scheduler_url}/api/internal/scheduler/agents/register",
            json=payload,
            headers={"x-internal-token": _expected_token()},
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
        try:
            get_pool().close()
        except Exception:
            pass


app = FastAPI(title="Audit Agent", version="0.1.0", lifespan=lifespan)

# 可观测性初始化
init_observability("audit-agent", app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/internal/agent/run")
async def run_agent(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    _verify_internal_token(request)

    task_type = str(body.get("task_type") or "").strip()
    if task_type != "audit.draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported task_type")

    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    draft_id = payload.get("draft_id")
    markdown_path = str(payload.get("markdown_path") or "").strip()

    if draft_id is None or not markdown_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing draft_id or markdown_path",
        )

    path = Path(markdown_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="markdown file not found")

    text = path.read_text(encoding="utf-8", errors="ignore")
    text = text[:30000]

    provider = get_default_provider()
    system_prompt = "你是内容审核助手。输出简短的风险点与建议。"
    user_prompt = f"请审核以下 Markdown 内容是否包含敏感信息、明显错误或不当表达，并给出建议：\n\n{text}"
    report = await provider.chat(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2)

    result = {
        "draft_id": int(draft_id),
        "task_id": body.get("task_id"),
        "trace_id": body.get("trace_id"),
        "decision": "needs_review",
        "report": report,
    }
    get_pool().set(f"audit:draft:{int(draft_id)}", result, ttl_seconds=86400 * 7)
    return {"ok": True, "task_type": task_type, "result": result}

