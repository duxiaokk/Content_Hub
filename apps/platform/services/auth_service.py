"""
功能摘要：本文件实现用户认证与注册的核心业务逻辑。

初学者指南：
这个文件是"登录注册流程的指挥中心"。它协调数据库查询、密码校验、数据写入等步骤，
但不直接处理网络请求，只专注于业务规则。如果你要修改注册规则（比如增加邮箱验证码），
重点关注 register_user() 函数，而界面和路由由 routers/auth.py 负责。

主要成员：
- authenticate_user(): 校验用户名和密码是否匹配数据库记录
- register_user(): 执行用户注册，包含数据校验、密码加密与数据库写入
- change_user_avatar(): 更新指定用户的头像路径
"""
from __future__ import annotations

from sqlalchemy.orm import Session

import security
from crud.crud_user import (
    create_user,
    get_user_by_username,
    get_user_by_username_or_email,
    update_user_avatar,
)


def authenticate_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not security.verify_password(password, user.hashed_password):
        return None
    return user


def register_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    avatar_path: str | None = None,
):
    username = (username or "").strip()
    email = (email or "").strip()
    password = (password or "").strip()

    if not username or not password:
        raise ValueError("Missing registration data")
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    email = email or f"{username}@local.invalid"
    existing = get_user_by_username_or_email(db, username, email)
    if existing:
        raise ValueError("Username or email already exists")

    hashed_pwd = security.get_password_hash(password)
    return create_user(
        db,
        username=username,
        email=email,
        hashed_password=hashed_pwd,
        avatar_path=avatar_path,
    )


def change_user_avatar(db: Session, *, username: str, avatar_path: str):
    user = get_user_by_username(db, username)
    if not user:
        raise LookupError("User not found")
    return update_user_avatar(db, user, avatar_path)
