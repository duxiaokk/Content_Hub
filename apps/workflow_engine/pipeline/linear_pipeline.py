from __future__ import annotations

from dataclasses import dataclass

from workflow_engine.registry.contracts import ContentAsset, FetchRequest, ProcessContext, PublishTarget
from workflow_engine.registry.plugin_registry import PluginRegistry
from workflow_engine.runtime.content_repository import ContentRepository
from workflow_engine.runtime.observability import WorkflowRunTrace


@dataclass(slots=True)
class LinearPipelineSpec:
    fetcher_name: str
    processor_name: str
    publisher_name: str
    fetch_request: FetchRequest
    process_context: ProcessContext
    publish_target: PublishTarget


class LinearPipelineRunner:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry
        self.repository = ContentRepository()

    async def run(self, spec: LinearPipelineSpec) -> list[dict]:
        trace = WorkflowRunTrace(
            run_id=spec.process_context.run_id or "linear-pipeline",
            workflow_name="content.pipeline.linear",
        )
        trace.mark_running()
        fetcher = self.registry.get_fetcher(spec.fetcher_name)
        processor = self.registry.get_processor(spec.processor_name)
        publisher = self.registry.get_publisher(spec.publisher_name)

        fetched_items = await fetcher.fetch(spec.fetch_request)
        results: list[dict] = []

        for item in fetched_items:
            content_id = self.repository.upsert_fetched_item(item)
            asset = ContentAsset(
                content_id=content_id,
                source_type=item.source_type,
                source_id=item.source_id,
                title=item.title,
                raw_content=item.raw_content,
                processed_content=None,
                source_url=item.source_url,
                metadata=dict(item.metadata),
            )
            process_result = await processor.process(asset, spec.process_context)
            self.repository.mark_processed(
                process_result.content,
                status=process_result.status,
                error_message=process_result.warnings[0] if process_result.warnings else None,
            )
            publish_result = await publisher.publish(process_result.content, spec.publish_target)
            self.repository.mark_published(
                process_result.content,
                target_name=spec.publish_target.target_name,
                result=publish_result,
            )
            results.append(
                {
                    "content_id": content_id,
                    "source_id": item.source_id,
                    "process_status": process_result.status,
                    "publish_status": publish_result.status,
                    "target_name": publish_result.target_name,
                    "run_id": spec.process_context.run_id,
                }
            )
            trace.record_item(
                succeeded=publish_result.status == "published",
                message=f"{item.source_type}:{item.source_id}",
                payload=results[-1],
            )

        trace.mark_finished(status="succeeded" if trace.items_failed == 0 else "partial")
        return results
