"""API Bearer Token 认证模块

支持两种认证方式（兼容现有 Cookie 认证）：
  1. Authorization: Bearer <token>  请求头
  2. Cookie 中的 access_token（现有方式）

用法:
    from core.api_auth import get_api_user, create_access_token

    @router.get("/me")
    async def me(user: Annotated[str, Depends(get_api_user)]):
        return success({"username": user})
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status

from core.config import settings
from core.error_codes import ErrorCode

SECRET_KEY = settings.secret_key
ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


def create_access_token(username: str, expires_delta: timedelta | None = None) -> str:
    """创建 Access Token（API 用）。"""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode(
        {"sub": username, "exp": expire, "iat": datetime.now(timezone.utc), "type": "access"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_token(token: str) -> str:
    """验证 JWT Token，返回用户名。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise jwt.InvalidTokenError("missing sub")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ErrorCode.TOKEN_EXPIRED, "data": None, "message": "Token 已过期"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ErrorCode.INVALID_TOKEN, "data": None, "message": "Token 无效"},
        )


async def get_api_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
    x_internal_token: Annotated[str | None, Header(alias="x-internal-token")] = None,
) -> str:
    """提取 API 用户身份（Bearer Token > Cookie > Internal Token > 401）。"""
    # 1. Bearer Token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            return verify_token(token)

    # 2. Cookie access_token
    if access_token:
        try:
            return verify_token(access_token)
        except HTTPException:
            pass  # Cookie token 失败则继续尝试

    # 3. Internal Token（内部服务调用）
    if x_internal_token:
        expected = os.getenv("INTERNAL_AGENT_TOKEN") or os.getenv("SCHEDULER_INTERNAL_TOKEN") or "local-dev-scheduler-token"
        if x_internal_token == expected:
            return "internal-service"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": ErrorCode.UNAUTHORIZED, "data": None, "message": "未提供有效认证"},
    )


async def get_optional_api_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """提取 API 用户身份，失败返回 None。"""
    try:
        return await get_api_user(authorization=authorization, access_token=access_token)
    except HTTPException:
        return None


# 便捷别名
ApiUser = Annotated[str, Depends(get_api_user)]
OptionalApiUser = Annotated[str | None, Depends(get_optional_api_user)]
