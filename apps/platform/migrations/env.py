"""
功能摘要：本文件配置数据库迁移工具 Alembic 的运行环境，负责比对模型差异并生成迁移脚本。

初学者指南：
这个文件是数据库结构变更的"自动化脚本引擎"。当你修改了 models.py 里的数据模型后，
Alembic（数据库迁移工具）会读取这里的配置来连接数据库，并自动生成升级脚本。
通常不需要修改这里的代码，除非更换数据库类型或修改迁移目录位置。

主要成员：
- run_migrations_offline(): 在不连接数据库的情况下生成迁移脚本
- run_migrations_online(): 通过数据库连接执行实际的结构变更
- target_metadata: 包含所有模型表结构元数据，供迁移工具比对差异
"""
from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

PLATFORM_DIR = Path(__file__).resolve().parents[1]
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

import models  # noqa: F401,E402
from core.config import settings  # noqa: E402
from database import Base  # noqa: E402


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.resolved_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
