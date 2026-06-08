"""统一 API 错误码规范

所有 API 响应均使用 `code` 字段表示业务状态：
  - 0: 成功
  - 4xxxx: 客户端错误（参数校验、认证、权限、资源不存在）
  - 5xxxx: 服务端错误（内部异常、外部依赖失败）
  - 6xxxx: 业务状态码（限流、降级、超时）

用法:
    from core.error_codes import ErrorCode
    raise HTTPException(status_code=400, detail={"code": ErrorCode.VALIDATION_ERROR, "message": "..."})
"""
from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    # ------------------------------------------------------------------
    # 成功
    # ------------------------------------------------------------------
    SUCCESS = 0

    # ------------------------------------------------------------------
    # 通用客户端错误 400xx
    # ------------------------------------------------------------------
    VALIDATION_ERROR = 40001
    """请求参数校验失败"""

    MISSING_REQUIRED_FIELD = 40002
    """缺少必填字段"""

    INVALID_FIELD_VALUE = 40003
    """字段值不合法"""

    # ------------------------------------------------------------------
    # 认证与授权 401xx / 403xx
    # ------------------------------------------------------------------
    UNAUTHORIZED = 40101
    """未登录或 Token 无效"""

    TOKEN_EXPIRED = 40102
    """Token 已过期，请刷新"""

    INVALID_TOKEN = 40103
    """Token 格式错误或签名无效"""

    FORBIDDEN = 40301
    """无权限执行此操作"""

    ROLE_NOT_ALLOWED = 40302
    """当前角色无权访问"""

    # ------------------------------------------------------------------
    # 资源 404xx / 409xx
    # ------------------------------------------------------------------
    NOT_FOUND = 40401
    """请求的资源不存在"""

    USER_NOT_FOUND = 40402
    """用户不存在"""

    POST_NOT_FOUND = 40403
    """文章不存在"""

    COMMENT_NOT_FOUND = 40404
    """评论不存在"""

    CONFLICT = 40901
    """资源冲突（如用户名已存在）"""

    DUPLICATE_LIKE = 40902
    """重复点赞"""

    # ------------------------------------------------------------------
    # 请求限制 429xx
    # ------------------------------------------------------------------
    RATE_LIMITED = 42901
    """请求频率超限"""

    # ------------------------------------------------------------------
    # 服务端错误 500xx
    # ------------------------------------------------------------------
    INTERNAL_ERROR = 50001
    """服务器内部错误"""

    DB_ERROR = 50002
    """数据库操作异常"""

    EXTERNAL_SERVICE_ERROR = 50003
    """外部服务调用失败"""

    LLM_SERVICE_ERROR = 50004
    """LLM 服务异常"""

    # ------------------------------------------------------------------
    # 业务状态码 600xx
    # ------------------------------------------------------------------
    DEGRADED = 60001
    """服务降级中，返回兜底结果"""

    TIMEOUT = 60002
    """处理超时"""

    CIRCUIT_OPEN = 60003
    """熔断器打开，请求被拒绝"""

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    @property
    def http_status(self) -> int:
        """根据错误码推断 HTTP 状态码。"""
        if self.value == 0:
            return 200
        if 40000 <= self.value < 50000:
            if self in (ErrorCode.UNAUTHORIZED, ErrorCode.TOKEN_EXPIRED, ErrorCode.INVALID_TOKEN):
                return 401
            if self in (ErrorCode.FORBIDDEN, ErrorCode.ROLE_NOT_ALLOWED):
                return 403
            if self in (ErrorCode.NOT_FOUND, ErrorCode.USER_NOT_FOUND,
                        ErrorCode.POST_NOT_FOUND, ErrorCode.COMMENT_NOT_FOUND):
                return 404
            if self == ErrorCode.CONFLICT or self.value in [40901, 40902]:
                return 409
            if self == ErrorCode.RATE_LIMITED:
                return 429
            return 400
        if 50000 <= self.value < 60000:
            return 500
        return 200

    @property
    def is_success(self) -> bool:
        return self == ErrorCode.SUCCESS
