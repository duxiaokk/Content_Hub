from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_config_requires_secret_key_without_explicit_dev_gate() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env.pop("SECRET_KEY", None)
    env.pop("ALLOW_INSECURE_DEV_SECRET", None)
    env.pop("CONTENT_HUB_ENV", None)
    env["PYTHONPATH"] = str(repo_root)

    result = subprocess.run(
        [sys.executable, "-c", "import apps.platform.core.config"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "SECRET_KEY is required" in (result.stderr or result.stdout)


def test_config_allows_dev_secret_with_explicit_gate() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env.pop("SECRET_KEY", None)
    env["CONTENT_HUB_ENV"] = "dev"
    env["ALLOW_INSECURE_DEV_SECRET"] = "true"
    env["PYTHONPATH"] = str(repo_root)

    result = subprocess.run(
        [sys.executable, "-c", "from apps.platform.core.config import settings; print(settings.secret_key)"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "local-dev-secret-key" in result.stdout
