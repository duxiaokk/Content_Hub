"""
功能摘要：本文件提供项目开发时常用的命令行脚本，用于代码检查、格式化和服务启动。

初学者指南：
这个文件相当于开发团队的"任务遥控器"。你在终端输入 python tasks.py run 就能启动网站，
输入 python tasks.py lint 就能检查代码规范。
如果你要为项目添加新的自动化命令（比如一键备份数据库），
可以参考下方 main() 函数中的子命令注册方式。

主要成员：
- cmd_run(): 启动网络服务，支持自动重载与自定义端口
- cmd_lint(): 调用 Ruff（代码检查工具）检查代码风格和潜在错误
- cmd_db_upgrade(): 执行数据库迁移升级，将表结构更新到最新版本
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _run(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT)
    return int(completed.returncode)


def cmd_lint() -> int:
    return _run([sys.executable, "-m", "ruff", "check", "."])


def cmd_format(check: bool) -> int:
    command = [sys.executable, "-m", "ruff", "format", "."]
    if check:
        command.append("--check")
    return _run(command)


def cmd_test() -> int:
    return _run([sys.executable, "-m", "pytest", "-q"])


def cmd_run(host: str, port: int, reload: bool) -> int:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        command.append("--reload")
    return _run(command)


def cmd_db_upgrade(revision: str) -> int:
    return _run([sys.executable, "-m", "alembic", "upgrade", revision])


def main() -> int:
    parser = argparse.ArgumentParser(description="Project development tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("lint", help="Run Ruff import and error checks.")

    format_parser = subparsers.add_parser("format", help="Run Ruff formatter.")
    format_parser.add_argument("--check", action="store_true", help="Only check formatting.")

    subparsers.add_parser("test", help="Run the test suite.")

    run_parser = subparsers.add_parser("run", help="Start the FastAPI app with uvicorn.")
    run_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the dev server.")
    run_parser.add_argument("--port", type=int, default=8000, help="Port to bind the dev server.")
    run_parser.add_argument("--no-reload", action="store_true", help="Disable auto reload.")

    db_upgrade_parser = subparsers.add_parser(
        "db-upgrade", help="Apply Alembic migrations to the configured database."
    )
    db_upgrade_parser.add_argument("revision", nargs="?", default="head", help="Target revision.")

    args = parser.parse_args()

    if args.command == "lint":
        return cmd_lint()
    if args.command == "format":
        return cmd_format(args.check)
    if args.command == "test":
        return cmd_test()
    if args.command == "run":
        return cmd_run(args.host, args.port, reload=not args.no_reload)
    if args.command == "db-upgrade":
        return cmd_db_upgrade(args.revision)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
