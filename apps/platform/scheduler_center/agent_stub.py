from __future__ import annotations

import os
import time

from fastapi import FastAPI, HTTPException, Request, status

from scheduler_center.config import scheduler_settings


app = FastAPI(title="Agent Stub", version="0.1.0")


def _parse_float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None and value != "" else default
    except ValueError:
        return default


_DELAY_SECONDS = _parse_float(os.getenv("AGENT_STUB_DELAY_SECONDS"), 0.0)
_FORCE_ERROR = (os.getenv("AGENT_STUB_FORCE_ERROR") or "").strip().lower() in {"1", "true", "yes", "on"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.post("/api/internal/agent/run")
def run_task(request: Request, payload: dict):
    expected = scheduler_settings.scheduler_agent_token or scheduler_settings.scheduler_internal_token
    token = request.headers.get("x-internal-token")
    if expected and token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    if _DELAY_SECONDS > 0:
        time.sleep(_DELAY_SECONDS)
    if _FORCE_ERROR:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="forced error")
    return {"ok": True, "received": payload}

