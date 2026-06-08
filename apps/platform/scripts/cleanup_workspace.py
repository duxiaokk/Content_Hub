#!/usr/bin/env python3
"""Project cleanup helper with whitelist, backup, reporting and validation."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_WHITELIST = "configs/cleanup_whitelist.json"
DEFAULT_BACKUP_DIR = ".tmp/cleanup_backups"
DEFAULT_REPORT_DIR = ".tmp/cleanup_reports"
DEFAULT_RETENTION_DAYS = 7

DIRECTORY_RULES = {
    "__pycache__": "python-cache",
    ".pytest_cache": "python-cache",
    ".ruff_cache": "tool-cache",
    ".mypy_cache": "tool-cache",
    ".cache": "cache-dir",
    ".temp": "cache-dir",
    "dist": "build-output",
    "build": "build-output",
    "node_modules": "dependency-cache",
    ".idea": "ide-config",
    ".vscode": "ide-config",
}

DIRECTORY_GLOB_RULES = [
    (".venv_backup*", "backup-directory"),
    ("_backup*", "backup-directory"),
    ("*_backup*", "backup-directory"),
]

FILE_NAME_RULES = {
    ".DS_Store": "system-artifact",
    "Thumbs.db": "system-artifact",
}

FILE_GLOB_RULES = [
    ("*.pyc", "python-cache"),
    ("*.pyo", "python-cache"),
    ("*.log", "log-file"),
    ("*.bak", "backup-file"),
    ("*.tmp", "temporary-file"),
    ("*.old", "backup-file"),
    ("*.db-wal", "sqlite-runtime"),
    ("*.db-shm", "sqlite-runtime"),
]

TEMP_ARCHIVE_SUFFIXES = (
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
)
TEMP_ARCHIVE_KEYWORDS = ("temp", "tmp", "backup", "bak", "archive", "old")


@dataclass
class Candidate:
    relative_path: str
    kind: str
    category: str
    size_bytes: int


@dataclass
class ValidationResult:
    name: str
    status: str
    detail: str


@dataclass
class CleanupManifest:
    root: str
    generated_at: str
    total_candidates: int
    total_bytes: int
    candidates: list[Candidate]


IGNORED_COMPONENT_PATTERNS = (
    ".git",
    ".venv",
    ".venv_*",
    "venv",
    "env",
    "site-packages",
)

TEMP_EMPTY_DIR_NAMES = {".cache", ".temp", ".tmp", "tmp", "temp", "build", "dist"}


def to_posix(path: Path) -> str:
    return path.as_posix().removeprefix("./")


def size_to_text(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size_bytes} B"


def dir_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def load_whitelist(root: Path, whitelist_path: Path | None) -> dict:
    data = {"protected_paths": [], "protected_names": []}
    if whitelist_path is None:
        return data
    file_path = whitelist_path if whitelist_path.is_absolute() else root / whitelist_path
    if not file_path.exists():
        return data
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    data["protected_paths"] = raw.get("protected_paths", [])
    data["protected_names"] = raw.get("protected_names", [])
    return data


def is_protected(relative_path: str, name: str, whitelist: dict) -> bool:
    if name in set(whitelist.get("protected_names", [])):
        return True
    for pattern in whitelist.get("protected_paths", []):
        if fnmatch.fnmatch(relative_path, pattern):
            return True
    return False


def is_temp_archive(path: Path) -> bool:
    suffixes = "".join(path.suffixes).lower()
    stem = path.stem.lower()
    if not any(suffixes.endswith(ext) for ext in TEMP_ARCHIVE_SUFFIXES):
        return False
    return any(keyword in stem for keyword in TEMP_ARCHIVE_KEYWORDS)


def should_ignore_path(relative_path: str) -> bool:
    if not relative_path:
        return False
    for part in relative_path.split("/"):
        for pattern in IGNORED_COMPONENT_PATTERNS:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def find_empty_directories(
    root: Path,
    whitelist: dict,
    ignored_roots: set[str],
    matched_roots: set[str],
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for current, dirs, files in os.walk(root, topdown=False):
        current_path = Path(current)
        if current_path == root:
            continue
        relative = to_posix(current_path.relative_to(root))
        if relative in ignored_roots or any(
            relative.startswith(f"{item}/") for item in ignored_roots
        ):
            continue
        if should_ignore_path(relative):
            continue
        if any(relative == item or relative.startswith(f"{item}/") for item in matched_roots):
            continue
        if is_protected(relative, current_path.name, whitelist):
            continue
        if current_path.name not in TEMP_EMPTY_DIR_NAMES and not any(
            keyword in relative.lower() for keyword in TEMP_ARCHIVE_KEYWORDS
        ):
            continue
        if not dirs and not files:
            candidates.append(
                Candidate(
                    relative_path=relative,
                    kind="directory",
                    category="empty-directory",
                    size_bytes=0,
                )
            )
    return candidates


def scan_candidates(root: Path, whitelist: dict) -> list[Candidate]:
    candidates: list[Candidate] = []
    ignored_roots = {
        DEFAULT_BACKUP_DIR.replace("\\", "/"),
        DEFAULT_REPORT_DIR.replace("\\", "/"),
        ".git",
        ".venv",
        ".venv_uv",
        "venv",
        "env",
    }
    matched_roots: set[str] = set()

    for current, dirs, files in os.walk(root, topdown=True):
        current_path = Path(current)
        relative_dir = (
            ""
            if current_path == root
            else to_posix(current_path.relative_to(root))
        )

        pruned_dirs: list[str] = []
        for dirname in list(dirs):
            child_path = current_path / dirname
            relative = to_posix(child_path.relative_to(root))
            if relative in ignored_roots or any(relative.startswith(f"{item}/") for item in ignored_roots):
                dirs.remove(dirname)
                continue
            if should_ignore_path(relative):
                dirs.remove(dirname)
                continue
            if is_protected(relative, dirname, whitelist):
                continue
            category = DIRECTORY_RULES.get(dirname)
            if category is None:
                for pattern, matched_category in DIRECTORY_GLOB_RULES:
                    if fnmatch.fnmatch(dirname, pattern):
                        category = matched_category
                        break
            if category:
                candidates.append(
                    Candidate(
                        relative_path=relative,
                        kind="directory",
                        category=category,
                        size_bytes=dir_size(child_path),
                    )
                )
                matched_roots.add(relative)
                pruned_dirs.append(dirname)
        for dirname in pruned_dirs:
            dirs.remove(dirname)

        for filename in files:
            file_path = current_path / filename
            relative = to_posix(file_path.relative_to(root))
            if should_ignore_path(relative):
                continue
            if is_protected(relative, filename, whitelist):
                continue
            category = FILE_NAME_RULES.get(filename)
            if category is None:
                for pattern, matched_category in FILE_GLOB_RULES:
                    if fnmatch.fnmatch(filename, pattern):
                        category = matched_category
                        break
            if category is None and is_temp_archive(file_path):
                category = "temporary-archive"
            if category is None:
                continue
            candidates.append(
                Candidate(
                    relative_path=relative,
                    kind="file",
                    category=category,
                    size_bytes=file_path.stat().st_size,
                )
            )

    candidates.extend(find_empty_directories(root, whitelist, ignored_roots, matched_roots))
    candidates.sort(key=lambda item: (item.category, item.relative_path))
    return candidates


def build_manifest(root: Path, candidates: list[Candidate]) -> CleanupManifest:
    total_bytes = sum(item.size_bytes for item in candidates)
    return CleanupManifest(
        root=str(root),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        total_candidates=len(candidates),
        total_bytes=total_bytes,
        candidates=candidates,
    )


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_paths(report_dir: Path) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = report_dir / f"cleanup_manifest_{stamp}.json"
    report_path = report_dir / f"cleanup_report_{stamp}.md"
    return manifest_path, report_path


def write_outputs(manifest: CleanupManifest, manifest_path: Path, report_path: Path) -> None:
    payload = asdict(manifest)
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    grouped: dict[str, list[Candidate]] = {}
    for candidate in manifest.candidates:
        grouped.setdefault(candidate.category, []).append(candidate)

    lines = [
        "# 项目临时文件扫描报告",
        "",
        f"- 项目根目录: `{manifest.root}`",
        f"- 生成时间: `{manifest.generated_at}`",
        f"- 待清理项目数: `{manifest.total_candidates}`",
        f"- 预计释放空间: `{size_to_text(manifest.total_bytes)}`",
        "",
        "## 分类清单",
        "",
    ]

    for category in sorted(grouped):
        items = grouped[category]
        category_size = sum(item.size_bytes for item in items)
        lines.append(f"### {category}")
        lines.append(f"- 数量: `{len(items)}`")
        lines.append(f"- 空间: `{size_to_text(category_size)}`")
        for item in items:
            lines.append(
                f"- `{item.relative_path}` ({item.kind}, {size_to_text(item.size_bytes)})"
            )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def print_manifest_summary(manifest: CleanupManifest) -> None:
    print(f"项目根目录: {manifest.root}")
    print(f"待清理项目数: {manifest.total_candidates}")
    print(f"预计释放空间: {size_to_text(manifest.total_bytes)}")
    for candidate in manifest.candidates[:20]:
        print(
            f" - [{candidate.category}] {candidate.relative_path} "
            f"({candidate.kind}, {size_to_text(candidate.size_bytes)})"
        )
    if manifest.total_candidates > 20:
        print(f" ... 其余 {manifest.total_candidates - 20} 项已写入报告")


def prompt_for_cleanup() -> bool:
    reply = input("请输入 DELETE 确认批量删除，其他输入将取消: ").strip()
    return reply == "DELETE"


def purge_expired_backups(backup_root: Path, retention_days: int) -> list[Path]:
    removed: list[Path] = []
    if not backup_root.exists():
        return removed
    expire_before = time.time() - retention_days * 86400
    for child in backup_root.iterdir():
        try:
            if child.stat().st_mtime >= expire_before:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed.append(child)
        except FileNotFoundError:
            continue
    return removed


def backup_candidates(root: Path, candidates: Iterable[Candidate], backup_root: Path) -> Path:
    session_dir = ensure_dir(backup_root / datetime.now().strftime("%Y%m%d_%H%M%S"))
    for item in candidates:
        source = root / item.relative_path
        target = session_dir / item.relative_path
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    return session_dir


def delete_candidates(root: Path, candidates: Iterable[Candidate]) -> list[str]:
    deleted: list[str] = []
    for item in candidates:
        target = root / item.relative_path
        if not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        deleted.append(item.relative_path)
    return deleted


def syntax_check(paths: Iterable[Path]) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for path in paths:
        if not path.exists():
            results.append(ValidationResult(path.name, "fail", "关键文件不存在"))
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
            results.append(ValidationResult(path.name, "pass", "语法检查通过"))
        except Exception as exc:  # pragma: no cover - defensive
            results.append(ValidationResult(path.name, "fail", f"语法检查失败: {exc}"))
    return results


def validate_project(root: Path, whitelist: dict) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    protected_samples = [
        "main.py",
        "database.py",
        "models.py",
        "security.py",
        "pyproject.toml",
        "requirements.txt",
        "alembic.ini",
        "frontend/package.json",
        "frontend/src/main.tsx",
        "scheduler_center/main.py",
    ]
    for relative in protected_samples:
        path = root / relative
        if path.exists():
            results.append(ValidationResult(relative, "pass", "关键路径存在"))
        else:
            results.append(ValidationResult(relative, "fail", "关键路径缺失"))

    python_targets = {
        "main.py": root / "main.py",
        "database.py": root / "database.py",
        "models.py": root / "models.py",
        "security.py": root / "security.py",
        "scheduler_center/main.py": root / "scheduler_center" / "main.py",
    }
    for label, path in python_targets.items():
        if not path.exists():
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
            results.append(ValidationResult(label, "pass", "语法检查通过"))
        except Exception as exc:  # pragma: no cover - defensive
            results.append(ValidationResult(label, "fail", f"语法检查失败: {exc}"))

    protected_count = len(whitelist.get("protected_paths", []))
    results.append(
        ValidationResult(
            "whitelist",
            "pass",
            f"已加载 {protected_count} 条白名单规则",
        )
    )
    return results


def print_validation(results: list[ValidationResult]) -> bool:
    failed = False
    print("\n校验结果:")
    for item in results:
        print(f" - [{item.status}] {item.name}: {item.detail}")
        if item.status == "fail":
            failed = True
    return not failed


def run_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    whitelist = load_whitelist(root, Path(args.whitelist) if args.whitelist else None)
    report_dir = ensure_dir((root / args.report_dir).resolve())
    manifest_path, report_path = report_paths(report_dir)

    candidates = scan_candidates(root, whitelist)
    manifest = build_manifest(root, candidates)
    write_outputs(manifest, manifest_path, report_path)
    print_manifest_summary(manifest)
    print(f"清单文件: {manifest_path}")
    print(f"报告文件: {report_path}")
    return 0


def run_clean(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    whitelist = load_whitelist(root, Path(args.whitelist) if args.whitelist else None)
    report_dir = ensure_dir((root / args.report_dir).resolve())
    backup_root = ensure_dir((root / args.backup_dir).resolve())
    removed_backups = purge_expired_backups(backup_root, args.retention_days)

    candidates = scan_candidates(root, whitelist)
    manifest = build_manifest(root, candidates)
    manifest_path, report_path = report_paths(report_dir)
    write_outputs(manifest, manifest_path, report_path)
    print_manifest_summary(manifest)
    print(f"清单文件: {manifest_path}")
    print(f"报告文件: {report_path}")

    if not candidates:
        print("没有匹配到待清理文件。")
        print_validation(validate_project(root, whitelist))
        return 0

    if not args.yes and not prompt_for_cleanup():
        print("已取消删除操作。")
        return 1

    backup_dir = backup_candidates(root, candidates, backup_root)
    print(f"备份目录: {backup_dir}")
    deleted = delete_candidates(root, candidates)
    print(f"已删除 {len(deleted)} 项，释放空间约 {size_to_text(manifest.total_bytes)}")
    if removed_backups:
        print(f"已清理过期备份 {len(removed_backups)} 项")

    validation = validate_project(root, whitelist)
    validation_ok = print_validation(validation)
    return 0 if validation_ok else 2


def run_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    whitelist = load_whitelist(root, Path(args.whitelist) if args.whitelist else None)
    results = validate_project(root, whitelist)
    return 0 if print_validation(results) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="扫描并清理项目中的临时文件。")
    parser.add_argument("--root", default=".", help="项目根目录，默认当前目录")
    parser.add_argument("--whitelist", default=DEFAULT_WHITELIST, help="白名单配置文件")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR, help="备份输出目录")
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR, help="报告输出目录")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help="备份保留天数，默认 7 天",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scan", help="仅扫描并生成待清理清单")

    clean_parser = subparsers.add_parser("clean", help="扫描、备份并执行清理")
    clean_parser.add_argument("--yes", action="store_true", help="跳过交互确认")

    subparsers.add_parser("verify", help="检查核心路径与关键 Python 文件语法")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "scan":
        return run_scan(args)
    if args.command == "clean":
        return run_clean(args)
    if args.command == "verify":
        return run_verify(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
