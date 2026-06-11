from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_no_legacy_paths_module_exists() -> None:
    assert not (ROOT / "apps" / "workflow_engine" / "runtime" / "legacy_paths.py").exists()


def test_platform_console_service_has_no_ado_repost_path_fallback() -> None:
    console_service = (ROOT / "apps" / "platform" / "services" / "console_service.py").read_text(encoding="utf-8")
    assert "ADO_REPOST_DIR" not in console_service
    assert "processed.json" not in console_service


def test_workflow_engine_source_has_no_ado_repost_imports() -> None:
    workflow_root = ROOT / "apps" / "workflow_engine"
    for path in workflow_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "test_architecture_boundaries.py":
            continue
        content = path.read_text(encoding="utf-8")
        assert "ado_repost" not in content, f"unexpected ado_repost reference in {path}"
