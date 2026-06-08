from __future__ import annotations

from fastapi import HTTPException, Request, status

from scheduler_center.config import scheduler_settings


def verify_internal_token(request: Request) -> None:
    token = request.headers.get("x-internal-token")
    if not token or token != scheduler_settings.scheduler_internal_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

