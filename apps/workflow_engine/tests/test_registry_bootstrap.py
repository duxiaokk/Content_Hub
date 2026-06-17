from __future__ import annotations

import os
import sys
from pathlib import Path


def test_build_default_registry_registers_components() -> None:
    os.environ["SECRET_KEY"] = "test-secret-key"
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from apps.workflow_engine.registry.bootstrap import build_default_registry
    from apps.workflow_engine.registry.static_registry import registry

    build_default_registry()

    assert "cnblogs" in registry.fetchers
    assert "bilibili" in registry.fetchers
    assert "github_trending" in registry.fetchers
    assert "reddit" in registry.fetchers
    assert "rewrite" in registry.processors
    assert "blog" in registry.publishers
