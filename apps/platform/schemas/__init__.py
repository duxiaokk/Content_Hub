"""
功能摘要：将数据模式层的常用类统一暴露，简化其他模块的导入路径。

初学者指南：
这个文件让其他模块可以从 schemas 包直接导入所需的数据类，
而不需要记住每个类具体定义在哪个子文件。
如果新增了常用的数据验证类，可以在上方补充导入并加入 __all__ 列表。

主要成员：
- UserCreate: 用户注册数据类
- PostCreate: 文章创建数据类
- AuthResponse: 身份验证响应数据类
"""
from schemas.agent import AgentDraftIngestRequest, AgentDraftResponse, AgentDraftUpdateRequest
from schemas.pipeline import (
    LinearPipelineFetchRequest,
    LinearPipelineProcessContext,
    LinearPipelinePublishTarget,
    LinearPipelineRunRequest,
)
from schemas.post import ArticleCreate, PostBase, PostCreate
from schemas.user import AuthResponse, UserBase, UserCreate, UserLogin, UserOut

__all__ = [
    "ArticleCreate",
    "AgentDraftIngestRequest",
    "AgentDraftResponse",
    "AgentDraftUpdateRequest",
    "AuthResponse",
    "LinearPipelineFetchRequest",
    "LinearPipelineProcessContext",
    "LinearPipelinePublishTarget",
    "LinearPipelineRunRequest",
    "PostBase",
    "PostCreate",
    "UserBase",
    "UserCreate",
    "UserLogin",
    "UserOut",
]
