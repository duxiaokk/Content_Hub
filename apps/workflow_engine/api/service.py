from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from apps.ai_processor.api.service import AIProcessingService
from apps.ai_processor.runtime.config import load_ai_processor_config
from apps.platform.database import SessionLocal
from apps.platform.models import ContentItem, PublishRecord, WorkflowRun
from apps.workflow_engine.pipeline.filter_node import FilterNode
from apps.workflow_engine.registry.contracts import ContentAsset, ProcessContext, ReviewItem
from apps.workflow_engine.registry.static_registry import RADAR_PIPELINE_STEPS
from apps.workflow_engine.runtime.content_repository import ContentQuery, ContentRepository
from apps.workflow_engine.runtime.observability import WorkflowRunTrace


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowEngineService:
    def __init__(self) -> None:
        self._repository = ContentRepository()
        self._filter_node = FilterNode()

    async def run_radar_pipeline(self, request: dict[str, Any]) -> dict[str, Any]:
        db: Session = SessionLocal()
        try:
            source_type = request.get("source_type")
            stop_on_error = bool(request.get("stop_on_error", False))
            run_id = str(request.get("run_id") or str(uuid.uuid4()))
            trace = WorkflowRunTrace(run_id=run_id, workflow_name="radar_pipeline")
            trace.mark_running()
            workflow_run = WorkflowRun(
                workflow_name="radar_pipeline",
                trigger_type=str(request.get("trigger_type") or "manual"),
                status="running",
                started_at=trace.started_at,
                trace_payload=trace.snapshot(),
            )
            db.add(workflow_run)
            db.commit()
            db.refresh(workflow_run)

            def persist_trace(*, status: str | None = None, error_summary: str | None = None) -> None:
                if status:
                    workflow_run.status = status
                workflow_run.finished_at = trace.finished_at
                workflow_run.items_total = trace.items_total
                workflow_run.items_succeeded = trace.items_succeeded
                workflow_run.items_failed = trace.items_failed
                workflow_run.error_summary = error_summary or trace.error_summary
                workflow_run.trace_payload = trace.snapshot()
                db.add(workflow_run)
                db.commit()

            trace.log_step_start("fetch", items_in=0)
            items = db.query(ContentItem).filter(ContentItem.pipeline_status == "fetched")
            if source_type:
                items = items.filter(ContentItem.source_type == source_type)
            rows = list(items.order_by(ContentItem.id.asc()).limit(int(request.get("limit", 20))).all())
            trace.log_step_end("fetch", status="success", items_out=len(rows))

            assets = [
                ContentAsset(
                    content_id=row.id,
                    source_type=row.source_type,
                    source_id=row.source_id,
                    title=row.title,
                    raw_content=row.raw_content,
                    processed_content=row.processed_content,
                    source_url=row.source_url,
                    metadata={},
                )
                for row in rows
            ]

            trace.log_step_start("dedup_filter", items_in=len(assets))
            filter_result = await self._filter_node.apply(assets, dict(request.get("filter_config") or {}))
            trace.log_step_end("dedup_filter", status="success", items_out=len(filter_result.items))
            ai_service = AIProcessingService(db, load_ai_processor_config())
            review_items: list[ReviewItem] = []
            errors: list[dict[str, Any]] = []

            trace.log_step_start("process", items_in=len(filter_result.items))
            for asset in filter_result.items:
                try:
                    process_result = await ai_service.process_content_item(
                        int(asset.content_id),
                        ProcessContext(
                            run_id=run_id,
                            options=dict(request.get("process_options") or {}),
                        ),
                    )
                    trace.log_token_usage(process_result.cost_tokens)
                    trace.record_item(
                        succeeded=True,
                        message="content processed",
                        payload={"content_id": asset.content_id, "tokens": process_result.cost_tokens},
                    )
                except Exception as exc:
                    errors.append({"node": "process", "content_id": asset.content_id, "error": str(exc)})
                    trace.record_item(
                        succeeded=False,
                        message="content processing failed",
                        payload={"content_id": asset.content_id, "error": str(exc)},
                    )
                    if stop_on_error:
                        break
                    continue

                db.refresh(rows[[row.id for row in rows].index(asset.content_id)])
                refreshed = db.query(ContentItem).filter(ContentItem.id == asset.content_id).first()
                review_items.append(
                    ReviewItem(
                        content_item_id=int(refreshed.id),
                        title=refreshed.title,
                        original_url=refreshed.source_url or "",
                        summary=refreshed.summary,
                        rewritten_title=refreshed.rewritten_title,
                        rewritten_content=refreshed.rewritten_content,
                        score=float(refreshed.score or 0),
                        tags=json.loads(refreshed.tags_json or "[]"),
                        category=process_result.content.metadata.get("category"),
                        status="pending",
                    )
                )
            trace.log_step_end(
                "process",
                status="failed" if errors and stop_on_error else "success",
                items_out=len(review_items),
                error=errors[0]["error"] if errors and stop_on_error else None,
            )

            trace.log_step_start("review_prepare", items_in=len(review_items))
            trace.log_step_end("review_prepare", status="success", items_out=len(review_items))

            trace.error_summary = "; ".join(error["error"] for error in errors[:3]) or None
            trace.mark_finished(status="failed" if errors and stop_on_error else "success")
            persist_trace(status=trace.status, error_summary=trace.error_summary)

            return {
                "pipeline": "radar_pipeline",
                "run_id": run_id,
                "workflow_run_id": workflow_run.id,
                "steps": RADAR_PIPELINE_STEPS,
                "filtered_out": filter_result.filtered_out,
                "review_items": [asdict(item) for item in review_items],
                "errors": errors,
                "trace_payload": trace.snapshot(),
            }
        except Exception as exc:
            if "trace" in locals() and "workflow_run" in locals():
                trace.error_summary = str(exc)
                trace.mark_finished(status="failed")
                persist_trace(status="failed", error_summary=str(exc))
            raise
        finally:
            db.close()

    async def run_content_radar(self, request: dict[str, Any]) -> dict[str, Any]:
        """稳定领域能力入口，供 B 侧适配层调用。"""
        return await self.run_radar_pipeline(request)

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

    def should_skip_publish(self, *, content_item_id: int, target_type: str, run_id: str | None = None) -> bool:
        db: Session = SessionLocal()
        try:
            if run_id:
                existing_run_record = (
                    db.query(PublishRecord)
                    .filter(
                        PublishRecord.run_id == run_id,
                        PublishRecord.content_item_id == content_item_id,
                        PublishRecord.target_type == target_type,
                    )
                    .first()
                )
                if existing_run_record is not None:
                    return True

            existing_success = (
                db.query(PublishRecord)
                .filter(
                    PublishRecord.content_item_id == content_item_id,
                    PublishRecord.target_type == target_type,
                    PublishRecord.status == "success",
                )
                .first()
            )
            return existing_success is not None
        finally:
            db.close()
