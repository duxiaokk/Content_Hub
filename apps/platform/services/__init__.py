"""
功能摘要：将业务服务层的常用函数统一暴露，方便上层路由或命令直接导入。

初学者指南：
这个文件相当于业务层的"前台接待"。其他模块可以从 services 包直接导入需要的函数，
而不需要记住每个函数具体在哪个子文件。如果新增了常用的业务功能函数，
可以在上方补充导入并加入 __all__ 列表。

主要成员：
- authenticate_user: 用户认证
- register_user: 用户注册
- add_comment: 添加评论
- toggle_post_like: 切换文章点赞
"""
from services.auth_service import (
    authenticate_user as authenticate_user,
)
from services.auth_service import (
    change_user_avatar as change_user_avatar,
)
from services.auth_service import (
    register_user as register_user,
)
from services.comment_service import (
    add_comment as add_comment,
)
from services.comment_service import (
    comment_to_dict as comment_to_dict,
)
from services.comment_service import (
    edit_comment as edit_comment,
)
from services.comment_service import (
    list_comment_page as list_comment_page,
)
from services.comment_service import (
    remove_comment as remove_comment,
)
from services.comment_service import (
    toggle_comment_like as toggle_comment_like,
)
from services.post_service import (
    get_post_detail_payload as get_post_detail_payload,
)
from services.post_service import (
    remove_post as remove_post,
)
from services.post_service import (
    toggle_post_like as toggle_post_like,
)

__all__ = [
    "authenticate_user",
    "change_user_avatar",
    "register_user",
    "add_comment",
    "comment_to_dict",
    "edit_comment",
    "list_comment_page",
    "remove_comment",
    "toggle_comment_like",
    "get_post_detail_payload",
    "remove_post",
    "toggle_post_like",
]