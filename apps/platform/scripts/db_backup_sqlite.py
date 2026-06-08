#!/usr/bin/env python
"""SQLite 全量备份脚本

用法:
    python scripts/db_backup_sqlite.py                     # 备份到 ./backups/
    python scripts/db_backup_sqlite.py --output ./my_backup # 指定输出目录
    python scripts/db_backup_sqlite.py --compress           # 备份后 gzip 压缩

备份内容:
    - blog.db (平台主库)
    - scheduler.db (调度中心库)
    - content/agent_drafts/ (Agent 草稿 Markdown 文件)
    - image/ (用户上传图片)
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _utcnow_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")


def backup_sqlite_db(db_path: Path, backup_dir: Path, compress: bool) -> Path:
    """使用 SQLite 内置 .backup API 安全备份数据库。"""
    if not db_path.exists():
        print(f"[SKIP] {db_path} 不存在，跳过")
        return None

    backup_name = f"{db_path.stem}_{_utcnow_str()}.db"
    backup_path = backup_dir / backup_name

    conn = sqlite3.connect(str(db_path))
    try:
        bkp = sqlite3.connect(str(backup_path))
        conn.backup(bkp)
        bkp.close()
    finally:
        conn.close()

    if compress:
        gz_path = backup_path.with_suffix(backup_path.suffix + ".gz")
        with open(backup_path, "rb") as f_in:
            with gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        backup_path.unlink()
        backup_path = gz_path

    print(f"[OK] {db_path.name} → {backup_path.name}")
    return backup_path


def backup_directory(src_dir: Path, backup_dir: Path, compress: bool) -> Path | None:
    """备份整个目录为 tar.gz。"""
    if not src_dir.exists() or not any(src_dir.iterdir()):
        print(f"[SKIP] {src_dir} 不存在或为空，跳过")
        return None

    archive_name = f"{src_dir.name}_{_utcnow_str()}"
    archive_path = backup_dir / archive_name

    archive_fmt = "gztar" if compress else "tar"
    ext = ".tar.gz" if compress else ".tar"
    shutil.make_archive(
        str(archive_path),
        archive_fmt,
        root_dir=PROJECT_ROOT,
        base_dir=str(src_dir.relative_to(PROJECT_ROOT)),
    )
    final_path = Path(str(archive_path) + ext)
    print(f"[OK] {src_dir.name}/ → {final_path.name}")
    return final_path


def generate_manifest(backup_dir: Path, files: list[Path]) -> Path:
    """生成备份清单文件。"""
    manifest = {
        "backup_time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "project": "Ado_Jk Multi-Agent Orchestration Platform",
        "files": [
            {
                "name": f.name,
                "size_bytes": f.stat().st_size,
            }
            for f in files
            if f
        ],
    }
    manifest_path = backup_dir / f"manifest_{_utcnow_str()}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] manifest → {manifest_path.name}")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite 全量备份")
    parser.add_argument(
        "--output", default=str(PROJECT_ROOT / "backups"),
        help="备份输出目录 (默认: ./backups)"
    )
    parser.add_argument("--compress", action="store_true", help="压缩备份文件")
    args = parser.parse_args()

    backup_dir = Path(args.output)
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"开始备份 → {backup_dir}")
    print("-" * 50)

    results: list[Path] = []

    # 1. 数据库备份
    for db_name in ["blog.db", "scheduler.db"]:
        result = backup_sqlite_db(PROJECT_ROOT / db_name, backup_dir, args.compress)
        if result:
            results.append(result)

    # 2. 文件目录备份
    for dir_name in ["content/agent_drafts", "image"]:
        result = backup_directory(PROJECT_ROOT / dir_name, backup_dir, args.compress)
        if result:
            results.append(result)

    # 3. 生成清单
    manifest = generate_manifest(backup_dir, results)
    results.append(manifest)

    print("-" * 50)
    print(f"备份完成，共 {len(results)} 个文件 → {backup_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
