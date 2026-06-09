from __future__ import annotations

import importlib.util
import sys
import sysconfig
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]
_ADO_REPOST_SRC = _ROOT / "apps" / "ado_repost" / "src"
_PLATFORM_APP = _ROOT / "apps" / "platform"


def _load_stdlib_platform_module():
    stdlib_dir = Path(sysconfig.get_path("stdlib"))
    platform_file = stdlib_dir / "platform.py"
    spec = importlib.util.spec_from_file_location("_stdlib_platform", platform_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load stdlib platform module from {platform_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_legacy_paths() -> None:
    sys.modules["platform"] = _load_stdlib_platform_module()
    for path in (str(_ADO_REPOST_SRC), str(_PLATFORM_APP)):
        if path not in sys.path:
            sys.path.insert(0, path)
