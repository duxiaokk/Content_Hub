"""
功能摘要：本文件负责密码加密、令牌生成与用户身份凭证的校验。

初学者指南：
这个文件是博客系统的"保安室"。用户注册时，密码会在这里加密后存进数据库；
用户登录后，系统会在这里签发临时身份令牌。
如果你要调整登录过期时间或更换加密算法，重点关注上方的配置常量和 create_token_pair() 函数。

主要成员：
- verify_password(): 对比用户输入的明文密码与数据库中的加密密码
- create_token_pair(): 同时生成访问令牌和刷新令牌，用于保持登录状态
- decode_token(): 验证令牌是否有效，防止伪造的身份凭证
- get_current_user_from_cookie(): 从浏览器 Cookie（小型文本数据）中读取当前登录用户
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import HTTPException, Request
from jwt import InvalidTokenError
from passlib.context import CryptContext
from starlette import status

from core.config import settings

pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)

ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days
SECRET_KEY = settings.secret_key


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def _create_token(data: dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
    payload = dict(data)
    expire = datetime.now(timezone.utc) + expires_delta
    payload.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": token_type})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: dict[str, Any]) -> str:
    return _create_token(data, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), "access")


def create_refresh_token(data: dict[str, Any]) -> str:
    return _create_token(data, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), "refresh")


def create_token_pair(data: dict[str, Any]) -> dict[str, str]:
    return {
        "access_token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
    }


def decode_token(token: str, expected_type: Optional[str] = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录") from exc

    token_type = payload.get("type")
    if expected_type and token_type != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    return payload


def get_current_user_from_cookie(request: Request) -> str:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    scheme, _, param = token.partition(" ")
    actual_token = param if scheme.lower() == "bearer" else token
    payload = decode_token(actual_token, expected_type="access")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    return str(username)
