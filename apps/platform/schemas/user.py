"""
功能摘要：本文件定义用户注册、登录与信息展示的数据结构。

初学者指南：
这个文件专门规定"用户相关接口的数据格式"。
比如注册时密码至少要 8 位且包含数字，这些信息都由 Pydantic（数据验证库）自动检查。
如果你要新增用户信息字段（比如昵称或手机号），在这里扩展对应的数据类即可。

主要成员：
- UserCreate: 用户注册请求模型，包含用户名、邮箱与密码校验规则
- UserLogin: 用户登录请求模型，包含用户名、密码与记住登录选项
- AuthResponse: 登录成功后的响应模型，返回消息、令牌类型与头像路径
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class UserLogin(BaseModel):
    username: str
    password: str
    remember: bool = False


class AuthResponse(BaseModel):
    message: str
    token_type: str
    avatar_path: str | None = None
