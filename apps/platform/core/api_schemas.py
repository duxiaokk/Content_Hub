"""统一 API 响应模型

所有 /api/v1/* 端点统一使用以下响应结构：

成功:
    {"code": 0, "data": {...}, "message": "ok"}

分页:
    {"code": 0, "data": {"items": [...], "total": 100, "page": 1, "page_size": 20}, "message": "ok"}

错误:
    {"code": 40001, "data": null, "message": "用户名不能为空"}

用法:
    from core.api_schemas import ApiResponse, success, error, paginated

    @router.get("/posts")
    async def list_posts() -> ApiResponse:
        return success({"items": posts})

    @router.get("/posts/{id}")
    async def get_post(id: int) -> ApiResponse:
        return error(ErrorCode.POST_NOT_FOUND, "文章不存在")
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from core.error_codes import ErrorCode

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 成功响应。"""

    code: int = Field(default=0, description="业务状态码，0 表示成功")
    data: T | None = Field(default=None, description="响应数据")
    message: str = Field(default="ok", description="状态描述")

    model_config = {"json_schema_extra": {"example": {"code": 0, "data": {"id": 1}, "message": "ok"}}}


class PaginatedData(BaseModel, Generic[T]):
    """分页数据结构。"""

    items: list[T] = Field(default_factory=list, description="数据列表")
    total: int = Field(default=0, description="总记录数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页大小")


class ApiError(BaseModel):
    """统一 API 错误响应（用于 OpenAPI 文档 schema）。"""

    code: int = Field(description="错误码")
    data: None = Field(default=None, description="始终为 null")
    message: str = Field(description="错误描述")


# ------------------------------------------------------------------
# 便捷工厂函数
# ------------------------------------------------------------------

def success(data: Any = None, message: str = "ok") -> ApiResponse:
    """构建成功响应。"""
    return ApiResponse(code=0, data=data, message=message)


def error(code: ErrorCode | int, message: str) -> ApiResponse:
    """构建错误响应。"""
    return ApiResponse(code=int(code), data=None, message=message)


def paginated(
    items: list[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
) -> ApiResponse:
    """构建分页响应。"""
    return ApiResponse(
        code=0,
        data=PaginatedData(items=items, total=total, page=page, page_size=page_size),
        message="ok",
    )
