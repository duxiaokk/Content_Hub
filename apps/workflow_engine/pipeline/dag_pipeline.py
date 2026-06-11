from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from workflow_engine.pipeline.linear_pipeline import LinearPipelineRunner, LinearPipelineSpec
from workflow_engine.registry.contracts import FetchRequest, ProcessContext, PublishTarget
from workflow_engine.registry.plugin_registry import PluginRegistry
from workflow_engine.runtime.observability import WorkflowRunTrace


@dataclass(slots=True)
class WorkflowNodeSpec:
    node_id: str
    stage: str
    component_name: str
    depends_on: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowGraphSpec:
    run_id: str
    workflow_name: str
    source_name: str
    nodes: list[WorkflowNodeSpec]
    lookback_hours: int = 24
    limit: int = 20


class DagWorkflowRunner:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry
        self._linear_runner = LinearPipelineRunner(registry)

    async def run(self, spec: WorkflowGraphSpec) -> dict[str, Any]:
        fetcher_name = self._get_stage_component(spec, "fetch")
        processor_name = self._get_stage_component(spec, "process")
        publisher_name = self._get_stage_component(spec, "publish")

        trace = WorkflowRunTrace(run_id=spec.run_id, workflow_name=spec.workflow_name)
        trace.mark_running()

        linear_spec = LinearPipelineSpec(
            fetcher_name=fetcher_name,
            processor_name=processor_name,
            publisher_name=publisher_name,
            fetch_request=FetchRequest(
                source_name=spec.source_name,
                lookback_hours=spec.lookback_hours,
                limit=spec.limit,
                options=self._stage_options(spec, "fetch"),
            ),
            process_context=ProcessContext(
                run_id=spec.run_id,
                options=self._stage_options(spec, "process"),
            ),
            publish_target=PublishTarget(
                target_name=publisher_name,
                options=self._stage_options(spec, "publish"),
            ),
        )

        results = await self._linear_runner.run(linear_spec)
        for item in results:
            succeeded = item.get("publish_status") == "published"
            trace.record_item(
                succeeded=succeeded,
                message=f"content {item.get('content_id')} processed",
                payload=item,
            )
        final_status = "succeeded" if trace.items_failed == 0 else "partial"
        trace.mark_finished(status=final_status)
        return {
            "run_id": spec.run_id,
            "workflow_name": spec.workflow_name,
            "status": final_status,
            "results": results,
            "trace": trace.snapshot(),
        }

    @staticmethod
    def _get_stage_component(spec: WorkflowGraphSpec, stage: str) -> str:
        for node in spec.nodes:
            if node.stage == stage:
                return node.component_name
        raise KeyError(f"workflow stage '{stage}' is required")

    @staticmethod
    def _stage_options(spec: WorkflowGraphSpec, stage: str) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for node in spec.nodes:
            if node.stage == stage:
                merged.update(node.options)
        return merged
