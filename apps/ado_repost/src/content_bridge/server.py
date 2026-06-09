from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, status

from content_bridge.main import run as run_once
from content_bridge.mempool import pool as mempool

from shared_memory.errors import LockTimeout


def _expected_internal_token() -> str:
    return (
        os.getenv("CONTENT_BRIDGE_INTERNAL_TOKEN")
        os.getenv("ADO_REPOST_INTERNAL_TOKEN")
        or os.getenv("SCHEDULER_INTERNAL_TOKEN")
        or "local-dev-scheduler-token"
    )


def _verify_internal_token(request: Request) -> None:
    token = request.headers.get("x-internal-token")
    if not token or token != _expected_internal_token():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def _make_idempotency_key(request: Request, body: dict[str, Any]) -> str:
    header = (request.headers.get("x-idempotency-key") or "").strip()
    if header:
        return header[:128]
    raw = str(body.get("task_id") or "").strip()
    return raw if raw else "content-bridge:default"


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    items = result.get("items")
    preview: list[dict[str, Any]] = []
    if isinstance(items, list):
        for item in items[:3]:
            if isinstance(item, dict):
                preview.append(
                    {
                        "source": item.get("source"),
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "published_at": item.get("published_at"),
                    }
                )
    publish_results = result.get("publish_results")
    published_ok = 0
    published_total = 0
    if isinstance(publish_results, list):
        published_total = len(publish_results)
        published_ok = sum(1 for r in publish_results if isinstance(r, dict) and r.get("ok") is True)
    return {
        "status": result.get("status"),
        "new_items": result.get("new_items"),
        "processed_items": result.get("processed_items"),
        "fetch_error": result.get("fetch_error"),
        "fetch_errors": result.get("fetch_errors"),
        "published_ok": published_ok,
        "published_total": published_total,
        "items_preview": preview,
        "processed_path": result.get("processed_path"),
        "article_payloads_path": result.get("article_payloads_path"),
    }


def _maybe_register() -> None:
    scheduler_url = (os.getenv("SCHEDULER_CENTER_URL") or "").strip().rstrip("/")
    base_url = (
        os.getenv("CONTENT_BRIDGE_BASE_URL")
        or os.getenv("ADO_REPOST_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if not scheduler_url or not base_url:
        return
    payload = {
        "agent_key": os.getenv("CONTENT_BRIDGE_AGENT_KEY") or os.getenv("ADO_REPOST_AGENT_KEY", "content-bridge"),
        "name": os.getenv("CONTENT_BRIDGE_AGENT_NAME") or os.getenv("ADO_REPOST_AGENT_NAME", "content-bridge"),
        "base_url": base_url,
        "task_types": ["content_bridge.run", "ado_repost.run"],
        "health_path": "/health",
        "capabilities": {"kind": "content_bridge"},
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


app = FastAPI(title="Content Bridge Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "mempool": mempool.health()}


@app.post("/api/internal/agent/run")
def run_agent(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    _verify_internal_token(request)

    idem_key = _make_idempotency_key(request, body)
    result_key = f"content-bridge:run-result:{idem_key}"
    lock_key = f"content-bridge:run-lock:{idem_key}"

    cached = mempool.get(result_key, default=None)
    if isinstance(cached, dict):
        return {"ok": True, "idempotency_key": idem_key, "cached": True, "result": cached}

    try:
        with mempool.lock(lock_key, ttl_seconds=900, timeout_seconds=0.1):
            cached2 = mempool.get(result_key, default=None)
            if isinstance(cached2, dict):
                return {"ok": True, "idempotency_key": idem_key, "cached": True, "result": cached2}

            payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
            dry_run = bool(payload.get("dry_run")) if isinstance(payload, dict) else False
            raw_result = run_once(dry_run=dry_run)
            summary = _summarize(raw_result)
            mempool.set(result_key, summary, ttl_seconds=3600)
            return {"ok": True, "idempotency_key": idem_key, "cached": False, "result": summary}
    except LockTimeout:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="busy")
