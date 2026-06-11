from __future__ import annotations

import sys
from pathlib import Path


APPS_ROOT = Path(__file__).resolve().parents[2]
apps_root_str = str(APPS_ROOT)
if apps_root_str not in sys.path:
    sys.path.insert(0, apps_root_str)
