from __future__ import annotations

import uuid
from typing import Any

from workflow_engine.pipeline import DagWorkflowRunner, WorkflowGraphSpec, WorkflowNodeSpec
from workflow_engine.registry.bootstrap import build_default_registry
from workflow_engine.registry.static_registry import registry
from workflow_engine.runtime.content_repository import ContentQuery, ContentRepository


class WorkflowEngineService:
    def __init__(self) -> None:
        build_default_registry()
        self._registry = registry
        self._repository = ContentRepository()
        self._dag_runner = DagWorkflowRunner(self._registry)

    async def run_content_workflow(
        self,
        *,
        workflow_name: str,
        source_name: str,
        fetcher_name: str,
        processor_name: str,
        publisher_name: str,
        lookback_hours: int = 24,
        limit: int = 20,
        options: dict[str, dict[str, Any]] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        node_options = options or {}
        graph = WorkflowGraphSpec(
            run_id=run_id or str(uuid.uuid4()),
            workflow_name=workflow_name,
            source_name=source_name,
            lookback_hours=lookback_hours,
            limit=limit,
            nodes=[
                WorkflowNodeSpec(
                    node_id="fetch",
                    stage="fetch",
                    component_name=fetcher_name,
                    options=dict(node_options.get("fetch") or {}),
                ),
                WorkflowNodeSpec(
                    node_id="process",
                    stage="process",
                    component_name=processor_name,
                    depends_on=["fetch"],
                    options=dict(node_options.get("process") or {}),
                ),
                WorkflowNodeSpec(
                    node_id="publish",
                    stage="publish",
                    component_name=publisher_name,
                    depends_on=["process"],
                    options=dict(node_options.get("publish") or {}),
                ),
            ],
        )
        return await self._dag_runner.run(graph)

    def list_content_items(
        self,
        *,
        review_status: str | None = None,
        publish_status: str | None = None,
        pipeline_status: str | None = None,
        source_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._repository.list_items(
            ContentQuery(
                review_status=review_status,
                publish_status=publish_status,
                pipeline_status=pipeline_status,
                source_type=source_type,
                limit=limit,
            )
        )
