
from __future__ import annotations

import importlib.util
import sys
import sysconfig
from pathlib import Path


def _ensure_stdlib_platform() -> None:
    existing = sys.modules.get("platform")
    if existing is not None and hasattr(existing, "python_implementation"):
        return

    stdlib_dir = Path(sysconfig.get_path("stdlib"))
    platform_file = stdlib_dir / "platform.py"
    spec = importlib.util.spec_from_file_location("_stdlib_platform_for_scheduler", platform_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load stdlib platform module from {platform_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["platform"] = module


_ensure_stdlib_platform()
