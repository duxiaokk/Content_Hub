"""API v1 — 认证接口

端点:
  POST   /api/v1/auth/login       — 登录获取 Token
  POST   /api/v1/auth/register    — 注册新用户
  POST   /api/v1/auth/refresh     — 刷新 Access Token
  GET    /api/v1/auth/me          — 获取当前用户信息
  POST   /api/v1/auth/avatar      — 上传用户头像
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import security
from core.api_auth import create_access_token
from core.api_schemas import ApiResponse, error, success
from core.error_codes import ErrorCode
from core.permissions import RequireUser, get_current_user, is_admin_username
from database import get_db
from services.auth_service import authenticate_user, change_user_avatar, register_user as register_user_service

router = APIRouter(prefix="/auth", tags=["Auth API v1"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AVATAR_DIR = os.path.join(BASE_DIR, "image", "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
ALLOWED_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

logger = logging.getLogger("auth_audit")


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")
    remember: bool = Field(default=False, description="是否记住登录")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=6, description="密码")


class LoginResponse(BaseModel):
    access_token: str = Field(description="访问令牌")
    token_type: str = Field(default="bearer")


class UserInfo(BaseModel):
    username: str
    role: str
    email: str | None = None
    avatar_path: str | None = None


# ------------------------------------------------------------------
# 端点
# ------------------------------------------------------------------

@router.post(
    "/login",
    response_model=ApiResponse,
    responses={401: {"description": "用户名或密码错误"}},
)
async def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """登录获取 JWT Token。"""
    user = authenticate_user(db, body.username, body.password)
    if not user:
        logger.warning("login failed: username=%s", body.username)
        return error(ErrorCode.UNAUTHORIZED, "用户名或密码错误")

    logger.info("login success: %s", user.username)
    access_token = create_access_token(user.username)

    # 设置 httpOnly Cookie（兼容现有前端）
    response.set_cookie(
        key="access_token", value=access_token,
        httponly=True, samesite="lax", path="/",
        max_age=60 * 60 * 24 * 30 if body.remember else None,
    )

    return success(LoginResponse(access_token=access_token).model_dump(), "登录成功")


@router.post(
    "/register",
    response_model=ApiResponse,
    responses={400: {"description": "注册参数错误"}, 409: {"description": "用户名已存在"}},
)
async def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户。"""
    try:
        new_user = register_user_service(
            db,
            username=body.username,
            email=body.email,
            password=body.password,
            avatar_path=None,
        )
    except ValueError as exc:
        msg = str(exc)
        code = ErrorCode.CONFLICT if "already" in msg.lower() else ErrorCode.VALIDATION_ERROR
        return error(code, msg)

    access_token = create_access_token(new_user.username)
    return success(
        {"username": new_user.username, "access_token": access_token},
        "注册成功",
    )


@router.post("/refresh", response_model=ApiResponse)
async def refresh(request: Request):
    """刷新 Access Token。"""
    token = request.cookies.get("refresh_token")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

    if not token:
        return error(ErrorCode.UNAUTHORIZED, "未提供刷新令牌")

    scheme, _, param = token.partition(" ")
    actual_token = param if scheme.lower() == "bearer" else token

    try:
        payload = security.decode_token(actual_token, expected_type="refresh")
    except Exception:
        return error(ErrorCode.INVALID_TOKEN, "刷新令牌无效或已过期")

    username = payload.get("sub")
    if not username:
        return error(ErrorCode.INVALID_TOKEN, "令牌无效")

    new_access_token = create_access_token(str(username))
    return success({"access_token": new_access_token, "token_type": "bearer"}, "刷新成功")


@router.get("/me", response_model=ApiResponse)
async def get_me(request: Request, db: Session = Depends(get_db)):
    """获取当前用户信息。"""
    username = await get_current_user(request)
    if not username:
        return error(ErrorCode.UNAUTHORIZED, "未登录")

    # 查找用户获取邮箱和头像
    from apps.platform.models import User
    user = db.query(User).filter(User.username == username).first()

    role = "admin" if is_admin_username(username) else "user"
    return success(UserInfo(
        username=username,
        role=role,
        email=user.email if user else None,
        avatar_path=user.avatar_path if user else None,
    ).model_dump())


@router.post("/avatar", response_model=ApiResponse,
    responses={400: {"description": "头像文件不合法"}, 401: {"description": "未登录"}},
)
async def update_avatar(
    request: Request,
    avatar: Annotated[UploadFile, File(description="头像文件 (jpg/png/gif/webp)")],
    db: Session = Depends(get_db),
):
    """上传用户头像。"""
    username = await get_current_user(request)
    if not username:
        return error(ErrorCode.UNAUTHORIZED, "未登录")

    if not avatar.filename:
        return error(ErrorCode.VALIDATION_ERROR, "请选择头像文件")

    ext = os.path.splitext(avatar.filename)[1].lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        return error(ErrorCode.INVALID_FIELD_VALUE, "仅支持 jpg/jpeg/png/gif/webp 格式")

    saved_name = f"{uuid.uuid4().hex}{ext}"
    rel_path = f"avatars/{saved_name}"
    abs_path = os.path.join(AVATAR_DIR, saved_name)

    file_data = await avatar.read()
    with open(abs_path, "wb") as buffer:
        buffer.write(file_data)

    try:
        change_user_avatar(db, username=username, avatar_path=rel_path)
    except LookupError:
        return error(ErrorCode.USER_NOT_FOUND, "用户不存在")

    return success({"avatar_path": rel_path}, "头像更新成功")
