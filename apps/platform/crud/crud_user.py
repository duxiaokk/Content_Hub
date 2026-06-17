"""
功能摘要：本文件封装用户相关的数据库增删改查操作。

初学者指南：
这个文件专门处理"用户数据"的读写。注册新账号、查询用户信息、更换头像
都通过这里的函数直接操作数据库。如果你要新增用户字段（比如手机号），
除了修改数据模型，也需要在这里添加对应的查询或更新函数。

主要成员：
- get_user_by_username(): 根据用户名查找单个用户
- create_user(): 将新用户数据写入数据库，包含加密后的密码
- update_user_avatar(): 更新指定用户的头像路径
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from apps.platform import models


def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_username_or_email(db: Session, username: str, email: str) -> Optional[models.User]:
    return (
        db.query(models.User)
        .filter((models.User.username == username) | (models.User.email == email))
        .first()
    )


def create_user(
    db: Session,
    *,
    username: str,
    email: str,
    hashed_password: str,
    avatar_path: str | None = None,
) -> models.User:
    user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        avatar_path=avatar_path,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_avatar(db: Session, user: models.User, avatar_path: str | None) -> models.User:
    user.avatar_path = avatar_path
    db.commit()
    db.refresh(user)
    return user
