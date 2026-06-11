from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


ROOT = Path(__file__).resolve().parents[2]


def test_orchestration_router_does_not_import_legacy_engine() -> None:
    content = (ROOT / "platform" / "scheduler_center" / "orchestration_router.py").read_text(encoding="utf-8")
    assert "from scheduler_center.orchestration_engine import OrchestrationEngine" not in content
    assert "get_orchestration_engine" not in content


def test_orchestration_router_uses_workflow_task_adapter() -> None:
    content = (ROOT / "platform" / "scheduler_center" / "orchestration_router.py").read_text(encoding="utf-8")
    assert 'WORKFLOW_TASK_TYPE = "content.workflow.run"' in content
    assert "db.query(SchedulerTask)" in content


def test_scheduler_main_does_not_create_legacy_orchestration_tables() -> None:
    content = (ROOT / "platform" / "scheduler_center" / "main.py").read_text(encoding="utf-8")
    assert "orchestration_models" not in content
    assert "OrchBase.metadata.create_all" not in content
