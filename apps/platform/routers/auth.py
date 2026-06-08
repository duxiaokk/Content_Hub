"""
功能摘要：本文件负责处理用户注册、登录、登出及头像上传等身份相关页面与接口。

初学者指南：
这个文件是博客系统的"用户大门"。当你点击登录或注册按钮时，
浏览器请求最终都会到达这里的函数。它既提供网页，也提供数据接口。
如果你要修改登录流程（比如增加验证码），重点关注 login_api() 和 register_user() 函数。

主要成员：
- login_api(): 验证用户名密码，成功后颁发身份令牌并写入浏览器 Cookie
- register_user(): 处理注册请求，保存头像并创建新用户记录
- refresh_token(): 使用刷新令牌换取新的访问令牌，延长登录有效期
"""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import security
from database import get_db
from schemas.user import AuthResponse, UserLogin
from services.auth_service import (
    authenticate_user,
    change_user_avatar,
)
from services.auth_service import (
    register_user as register_user_service,
)

router = APIRouter(tags=["Authentication"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
AVATAR_DIR = os.path.join(BASE_DIR, "image", "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
ALLOWED_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

logger = logging.getLogger("auth_audit")


def _apply_auth_cookies(
    response: Response, access_token: str, refresh_token: str | None, remember: bool
) -> None:
    access_cookie_kwargs = {
        "key": "access_token",
        "value": access_token,
        "httponly": True,
        "samesite": "lax",
        "path": "/",
    }
    if remember:
        access_cookie_kwargs["max_age"] = 60 * 60 * 24 * 30
    response.set_cookie(**access_cookie_kwargs)

    if remember and refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=60 * 60 * 24 * security.REFRESH_TOKEN_EXPIRE_DAYS,
        )
    else:
        response.delete_cookie("refresh_token", path="/")


@router.post("/login", response_model=AuthResponse)
async def login_api(data: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.username, data.password)
    if not user:
        logger.warning("login failed: username=%s", data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="\u7528\u6237\u540d\u6216\u5bc6\u7801\u9519\u8bef",
        )

    logger.info("login success: %s", user.username)
    access_token = security.create_access_token({"sub": user.username})
    refresh_token = security.create_refresh_token({"sub": user.username}) if data.remember else None
    _apply_auth_cookies(response, access_token, refresh_token, data.remember)
    return {"message": "Login successful", "token_type": "bearer"}


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/register-page", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")


async def _parse_register_request(
    request: Request,
) -> tuple[str | None, str | None, str | None, UploadFile | None]:
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        data = await request.json()
        return data.get("username"), data.get("email"), data.get("password"), None

    form = await request.form()
    avatar = form.get("avatar")
    if not isinstance(avatar, UploadFile):
        avatar = None
    return form.get("username"), form.get("email"), form.get("password"), avatar


async def _save_avatar_upload(avatar: UploadFile | None, *, required: bool) -> str | None:
    if not avatar or not avatar.filename:
        if required:
            raise HTTPException(status_code=400, detail="Please choose an avatar file")
        return None

    ext = os.path.splitext(avatar.filename)[1].lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail="Only jpg/jpeg/png/gif/webp avatars are supported"
        )

    saved_name = f"{uuid.uuid4().hex}{ext}"
    rel_path = f"avatars/{saved_name}"
    abs_path = os.path.join(AVATAR_DIR, saved_name)

    file_data = await avatar.read()
    with open(abs_path, "wb") as buffer:
        buffer.write(file_data)

    return rel_path.replace("\\", "/")


@router.post("/register", response_model=AuthResponse)
async def register_user(request: Request, db: Session = Depends(get_db)):
    username, email, password, avatar = await _parse_register_request(request)

    avatar_path = await _save_avatar_upload(avatar, required=False)
    try:
        new_user = register_user_service(
            db,
            username=username or "",
            email=email or "",
            password=password or "",
            avatar_path=avatar_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    access_token = security.create_access_token({"sub": new_user.username})
    wants_json = (
        "application/json" in (request.headers.get("content-type") or "").lower()
        or (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest"
    )

    if wants_json:
        response = JSONResponse(
            {
                "message": "Registration successful",
                "token_type": "bearer",
                "avatar_path": avatar_path,
            }
        )
        _apply_auth_cookies(response, access_token, None, remember=False)
        return response

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    _apply_auth_cookies(response, access_token, None, remember=False)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


@router.post("/refresh-token")
async def refresh_token(request: Request):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    scheme, _, param = token.partition(" ")
    actual_token = param if scheme.lower() == "bearer" else token
    payload = security.decode_token(actual_token, expected_type="refresh")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    new_access_token = security.create_access_token({"sub": str(username)})
    response = JSONResponse({"access_token": new_access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/profile/avatar")
async def update_profile_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    username = security.get_current_user_from_cookie(request)
    avatar_path = await _save_avatar_upload(avatar, required=True)
    try:
        change_user_avatar(db, username=username, avatar_path=avatar_path)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    return {"message": "Avatar updated", "avatar_path": avatar_path}
