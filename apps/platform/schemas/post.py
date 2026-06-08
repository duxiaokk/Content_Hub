"""
功能摘要：本文件定义文章相关的请求和响应数据结构。

初学者指南：
这个文件专门规定"创建文章时需要传什么字段"。
它使用 Pydantic（数据验证库）自动校验标题不能为空、评分必须在 0 到 5 之间等规则。
如果你要给文章增加新属性（比如封面图链接），在这里添加字段即可。

主要成员：
- PostBase: 文章基础模型，定义标题、内容、发布状态与评分
- PostCreate: 创建文章时的请求模型，目前直接继承基础模型
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PostBase(BaseModel):
    title: str = Field(..., min_length=1)
    content: str
    published: bool = True
    rating: Optional[int] = Field(None, ge=0, le=5)


class PostCreate(PostBase):
    pass


class ArticleCreate(PostBase):
    pass
