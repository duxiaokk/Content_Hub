"""
功能摘要：将配置模块的入口暴露给外部，简化其他代码的导入路径。

初学者指南：
这个文件让其他模块可以用 from core import settings 这种简洁方式导入配置。
如果你看到项目里有人直接从 core 包导入东西，入口就是这里。
通常不需要修改，除非新增需要对外暴露的子模块。

主要成员：
- settings: 从 core.config 导入的配置实例，供全项目使用
"""
from core.config import settings as settings

__all__ = [
    'settings',
]
