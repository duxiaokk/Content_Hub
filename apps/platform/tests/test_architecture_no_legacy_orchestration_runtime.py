from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


ROOT = Path(__file__).resolve().parents[2]


def test_platform_runtime_sources_do_not_use_legacy_orchestration_engine() -> None:
    runtime_files = [
        ROOT / "platform" / "scheduler_center" / "main.py",
        ROOT / "platform" / "scheduler_center" / "orchestration_router.py",
        ROOT / "platform" / "scheduler_center" / "dispatcher.py",
        ROOT / "platform" / "routers" / "internal_tasks.py",
        ROOT / "platform" / "services" / "console_service.py",
    ]
    for path in runtime_files:
        content = path.read_text(encoding="utf-8")
        assert "orchestration_engine" not in content, f"legacy orchestration engine leaked into {path}"


def test_platform_runtime_sources_use_workflow_engine_entrypoints() -> None:
    dispatcher = (ROOT / "platform" / "scheduler_center" / "dispatcher.py").read_text(encoding="utf-8")
    orchestration_router = (ROOT / "platform" / "scheduler_center" / "orchestration_router.py").read_text(encoding="utf-8")
    assert "ContentDomainClient" in dispatcher or "content_domain_client" in dispatcher
    assert "WorkflowEngineService" not in dispatcher
    assert 'WORKFLOW_TASK_TYPE = "content.workflow.run"' in orchestration_router


def test_legacy_layers_are_marked_frozen_compatibility() -> None:
    legacy_files = [
        ROOT / "platform" / "scheduler_center" / "orchestration_engine.py",
        ROOT / "platform" / "services" / "planner_service.py",
        ROOT / "platform" / "services" / "aggregator_service.py",
    ]
    for path in legacy_files:
        content = path.read_text(encoding="utf-8")
        assert "Compatibility layer only." in content
