"""角色模型与权限控制

角色层级: anonymous < user < admin

使用方式:
    from core.permissions import Role, require_role, require_admin

    @router.get("/admin/users")
    async def admin_only(user = Depends(require_admin)):
        ...

    @router.get("/profile")
    async def user_only(user = Depends(require_role(Role.USER))):
        ...
"""
from __future__ import annotations

import os
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from core.error_codes import ErrorCode


class Role(StrEnum):
    """角色定义。"""
    ANONYMOUS = "anonymous"
    USER = "user"
    ADMIN = "admin"


ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Ado_Jk")


# ------------------------------------------------------------------
# 用户身份提取
# ------------------------------------------------------------------

async def get_current_user(request: Request) -> str | None:
    """从 Cookie 或 Bearer 头提取当前用户名，失败返回 None。"""
    try:
        from security import get_current_user_from_cookie
        return await get_current_user_from_cookie(request)
    except Exception:
        pass

    # 也尝试从 Bearer Token 提取（SPA 前端通过 localStorage 发送）
    try:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            if token:
                from security import decode_token
                payload = decode_token(token, expected_type="access")
                username = payload.get("sub")
                if username:
                    return str(username)
    except Exception:
        pass

    return None


async def get_current_user_required(request: Request) -> str:
    """提取当前用户名，未登录抛出 401。"""
    user = await get_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ErrorCode.UNAUTHORIZED, "data": None, "message": "未登录"},
        )
    return user


async def get_current_role(request: Request) -> Role:
    """获取当前请求的角色。"""
    user = await get_current_user(request)
    if user is None:
        return Role.ANONYMOUS
    if user.replace("_", "").lower() == ADMIN_USERNAME.replace("_", "").lower():
        return Role.ADMIN
    return Role.USER


def is_admin_username(username: str | None) -> bool:
    """检查是否是管理员用户名。"""
    if not username:
        return False
    return username.replace("_", "").lower() == ADMIN_USERNAME.replace("_", "").lower()


# ------------------------------------------------------------------
# 依赖注入
# ------------------------------------------------------------------

def require_role(min_role: Role):
    """返回一个 FastAPI Depends，要求用户至少拥有 min_role 角色。"""

    async def _check(request: Request, current_user: Annotated[str, Depends(get_current_user_required)]) -> str:
        role = await get_current_role(request)

        role_order = {Role.ANONYMOUS: 0, Role.USER: 1, Role.ADMIN: 2}
        if role_order.get(role, -1) < role_order.get(min_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": ErrorCode.ROLE_NOT_ALLOWED, "data": None, "message": f"需要 {min_role} 权限"},
            )
        return current_user

    return _check


async def require_admin(current_user: Annotated[str, Depends(get_current_user_required)]) -> str:
    """要求管理员权限的依赖注入。"""
    if not is_admin_username(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": ErrorCode.ROLE_NOT_ALLOWED, "data": None, "message": "需要管理员权限"},
        )
    return current_user


# 便捷别名
RequireUser = Annotated[str, Depends(require_role(Role.USER))]
RequireAdmin = Annotated[str, Depends(require_admin)]
OptionalUser = Annotated[str | None, Depends(get_current_user)]
