"""
功能摘要：将数据操作层的常用函数统一暴露，方便上层业务导入。

初学者指南：
这个文件相当于数据操作层的"前台接待"。其他模块不需要记住每个函数具体在哪个文件，
直接从这里导入最常用的几个即可。如果新增了常用的数据库操作函数，
可以在上方补充导入并加入 __all__ 列表。

主要成员：
- create_post: 创建文章
- delete_post: 删除文章
- get_user_by_username: 按用户名查询用户
- update_post_like: 更新文章点赞状态
"""
from crud.crud_post import create_post, delete_post, get_post, get_posts, update_post_like
from crud.crud_user import get_user_by_username
from crud.crud_content_item import create_content_item, get_content_item_by_source, update_content_item

__all__ = [
    "create_content_item",
    "create_post",
    "delete_post",
    "get_content_item_by_source",
    "get_post",
    "get_posts",
    "get_user_by_username",
    "update_content_item",
    "update_post_like",
]
