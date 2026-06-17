from __future__ import annotations

import sys
from pathlib import Path


PLATFORM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PLATFORM_DIR.parent.parent

for path in (REPO_ROOT, PLATFORM_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
