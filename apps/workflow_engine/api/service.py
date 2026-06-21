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
from apps.platform.models import ContentItem, PublishRecord, ReviewQueue, WorkflowRun
from apps.platform.services.agent_memory_service import AgentMemoryService
from apps.platform.services.review_service import ReviewService
from apps.workflow_engine.pipeline import DagWorkflowRunner, WorkflowGraphSpec, WorkflowNodeSpec
from apps.workflow_engine.pipeline.filter_node import FilterNode
from apps.workflow_engine.registry.bootstrap import build_default_registry
from apps.workflow_engine.registry.contracts import ContentAsset, ProcessContext, ReviewItem
from apps.workflow_engine.registry.static_registry import RADAR_PIPELINE_STEPS
from apps.workflow_engine.registry.static_registry import registry as workflow_registry
from apps.workflow_engine.runtime.content_repository import ContentQuery, ContentRepository
from apps.workflow_engine.runtime.observability import WorkflowRunTrace


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowEngineService:
    def __init__(self) -> None:
        self._repository = ContentRepository()
        self._filter_node = FilterNode()
        self._ensure_registry_ready()

    @staticmethod
    def _ensure_registry_ready() -> None:
        if not workflow_registry.fetchers:
            build_default_registry()

    @staticmethod
    def _upsert_review_queue_entry(db: Session, item: ContentItem) -> ReviewQueue:
        row = db.query(ReviewQueue).filter(ReviewQueue.content_item_id == item.id).first()
        if row is None:
            row = ReviewQueue(content_item_id=item.id)
        row.candidate_title = item.rewritten_title
        row.candidate_content = item.rewritten_content
        row.status = "pending"
        row.reviewer = None
        row.review_note = None
        row.reviewed_at = None
        db.add(row)
        return row

    @staticmethod
    def _remember_workflow_outcome(
        db: Session,
        *,
        workflow_name: str,
        trace: WorkflowRunTrace,
        extra: dict[str, Any] | None = None,
    ) -> None:
        total = max(trace.items_total, 0)
        success_rate = 1.0 if total == 0 else round(trace.items_succeeded / total, 4)
        payload = {
            "run_id": trace.run_id,
            "status": trace.status,
            "items_total": trace.items_total,
            "items_succeeded": trace.items_succeeded,
            "items_failed": trace.items_failed,
            "success_rate": success_rate,
            "error_summary": trace.error_summary,
            "suggested_limit": 10 if success_rate < 0.5 else 20,
            "suggested_lookback_hours": 48 if success_rate < 0.5 else 24,
        }
        if extra:
            payload.update(extra)
        AgentMemoryService(db).record_workflow_outcome(
            workflow_name=workflow_name,
            payload=payload,
            source="workflow_engine",
        )

    @staticmethod
    def _build_review_failure_observations(quality_gate_results: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for result in quality_gate_results:
            quality_gate = result.get("quality_gate") or {}
            checks = list(quality_gate.get("checks") or [])
            for check in checks:
                if bool(check.get("passed")):
                    continue
                name = str(check.get("name") or "unknown")
                counts[name] = counts.get(name, 0) + 1
        top_reasons = [
            {"reason": reason, "count": count}
            for reason, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]
        return {"top_reasons": top_reasons[:5], "counts": counts}

    @staticmethod
    def _build_radar_observations(
        *,
        rows: list[ContentItem],
        filtered_count: int,
        review_items: list[ReviewItem],
        quality_gate_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fetched_count = len(rows)
        populated_count = sum(1 for row in rows if str(row.raw_content or "").strip())
        coverage_ratio = round(populated_count / fetched_count, 4) if fetched_count else 0.0
        process_scores = [float(item.score or 0.0) for item in review_items if item.score is not None]
        return {
            "fetch_quality": {
                "fetched_count": fetched_count,
                "content_populated_count": populated_count,
                "coverage_ratio": coverage_ratio,
                "filtered_count": filtered_count,
                "quality_score": coverage_ratio,
            },
            "tool_hit_rate": {"attempts": 0, "hits": 0, "hit_rate": 0.0},
            "process_quality": {
                "processed_count": len(review_items),
                "scored_count": len(process_scores),
                "average_quality_score": round(sum(process_scores) / len(process_scores), 4) if process_scores else 0.0,
            },
            "publish_success_rate": {},
            "review_failure_reasons": WorkflowEngineService._build_review_failure_observations(quality_gate_results),
        }

    @staticmethod
    def _build_next_run_suggestions(observations: dict[str, Any]) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        fetch_quality = dict(observations.get("fetch_quality") or {})
        process_quality = dict(observations.get("process_quality") or {})
        review_failures = dict(observations.get("review_failure_reasons") or {})
        if float(fetch_quality.get("quality_score") or 0.0) < 0.55:
            suggestions.append({"action": "add_tool_context", "reason": "low fetch quality"})
        if float(process_quality.get("average_quality_score") or 0.0) < 0.7:
            suggestions.append({"action": "tighten_rewrite_quality", "reason": "low process quality score"})
        if review_failures.get("top_reasons"):
            suggestions.append({"action": "enable_quality_gate", "reason": "review failures detected"})
        return suggestions

    async def run_radar_pipeline(self, request: dict[str, Any]) -> dict[str, Any]:
        db: Session = SessionLocal()
        try:
            source_type = request.get("source_type")
            fetch_run_id_value = request.get("fetch_run_id")
            fetch_run_id = int(fetch_run_id_value) if fetch_run_id_value is not None else None
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
            rows = [
                db.query(ContentItem).filter(ContentItem.id == int(item["id"])).first()
                for item in self._repository.list_items(
                    ContentQuery(
                        pipeline_status="fetched",
                        source_type=str(source_type) if source_type else None,
                        fetch_run_id=fetch_run_id,
                        limit=int(request.get("limit", 20)),
                    )
                )
            ]
            rows = [row for row in rows if row is not None]
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
            review_queue_ids: list[int] = []
            for item in rows:
                if item.pipeline_status != "processed":
                    continue
                item.review_status = "pending"
                queue_row = self._upsert_review_queue_entry(db, item)
                db.add(item)
                db.flush()
                if queue_row.id is not None:
                    review_queue_ids.append(int(queue_row.id))
            db.commit()
            trace.log_step_end("review_prepare", status="success", items_out=len(review_items))

            quality_gate_results: list[dict[str, Any]] = []
            review_options = dict(request.get("review_options") or {})
            if bool(review_options.get("enable_quality_gate")) and review_queue_ids:
                trace.log_step_start("quality_gate", items_in=len(review_queue_ids))
                review_service = ReviewService(db)
                for review_queue_id in review_queue_ids:
                    quality_gate_results.append(
                        review_service.auto_review(
                            int(review_queue_id),
                            reviewer=str(review_options.get("reviewer") or "quality-gate"),
                            use_tool=bool(review_options.get("use_tool")),
                            auto_approve=bool(review_options.get("auto_approve")),
                            auto_reject=bool(review_options.get("auto_reject", True)),
                        )
                )
                trace.log_step_end("quality_gate", status="success", items_out=len(quality_gate_results))

            observations = self._build_radar_observations(
                rows=rows,
                filtered_count=len(filter_result.filtered_out),
                review_items=review_items,
                quality_gate_results=quality_gate_results,
            )
            next_run_suggestions = self._build_next_run_suggestions(observations)
            trace.error_summary = "; ".join(error["error"] for error in errors[:3]) or None
            trace.mark_finished(status="failed" if errors and stop_on_error else "success")
            self._remember_workflow_outcome(
                db,
                workflow_name="radar_pipeline",
                trace=trace,
                extra={
                    "review_queue_count": len(review_queue_ids),
                    "quality_gate_count": len(quality_gate_results),
                    "observations": observations,
                    "reasoning_decisions": [
                        {
                            "stage": "publish",
                            "decision": "enter_quality_gate" if bool(review_options.get("enable_quality_gate")) else "review_queue_only",
                            "reason": "request review options",
                        }
                    ],
                    "next_run_suggestions": next_run_suggestions,
                },
            )
            persist_trace(status=trace.status, error_summary=trace.error_summary)

            return {
                "pipeline": "radar_pipeline",
                "run_id": run_id,
                "workflow_run_id": workflow_run.id,
                "steps": RADAR_PIPELINE_STEPS,
                "filtered_out": filter_result.filtered_out,
                "review_items": [asdict(item) for item in review_items],
                "review_queue_ids": review_queue_ids,
                "quality_gate_results": quality_gate_results,
                "observations": observations,
                "next_run_suggestions": next_run_suggestions,
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

    async def run_content_workflow(
        self,
        *,
        workflow_name: str,
        source_name: str,
        fetcher_name: str,
        processor_name: str,
        publisher_name: str,
        lookback_hours: int,
        limit: int,
        options: dict[str, Any] | None = None,
        nodes: list[dict[str, Any]] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_run_id = str(run_id or str(uuid.uuid4()))
        resolved_options = dict(options or {})
        resolved_nodes = list(nodes or [])
        runner = DagWorkflowRunner(workflow_registry)
        if resolved_nodes:
            graph_nodes = [
                WorkflowNodeSpec(
                    node_id=str(node.get("node_id") or f"node-{index}"),
                    stage=str(node.get("stage") or ""),
                    component_name=str(node.get("component_name") or ""),
                    depends_on=[str(dep) for dep in node.get("depends_on", []) if str(dep).strip()],
                    options=dict(node.get("options") or {}),
                )
                for index, node in enumerate(resolved_nodes, start=1)
            ]
        else:
            graph_nodes = [
                WorkflowNodeSpec(
                    node_id="fetch",
                    stage="fetch",
                    component_name=fetcher_name,
                    options=dict(resolved_options.get("fetch") or {}),
                ),
                WorkflowNodeSpec(
                    node_id="process",
                    stage="process",
                    component_name=processor_name,
                    depends_on=["fetch"],
                    options=dict(resolved_options.get("process") or {}),
                ),
                WorkflowNodeSpec(
                    node_id="publish",
                    stage="publish",
                    component_name=publisher_name,
                    depends_on=["process"],
                    options=dict(resolved_options.get("publish") or {}),
                ),
            ]
        result = await runner.run(
            WorkflowGraphSpec(
                run_id=resolved_run_id,
                workflow_name=workflow_name,
                source_name=source_name,
                lookback_hours=lookback_hours,
                limit=limit,
                nodes=graph_nodes,
            )
        )
        errors = list(result.get("errors") or [])
        trace_snapshot = dict(result.get("trace") or {})
        trace = WorkflowRunTrace(run_id=resolved_run_id, workflow_name=workflow_name)
        trace.items_total = int(trace_snapshot.get("items_total") or len(result.get("results") or []))
        trace.items_succeeded = int(trace_snapshot.get("items_succeeded") or 0)
        trace.items_failed = int(trace_snapshot.get("items_failed") or len(errors))
        trace.error_summary = str(trace_snapshot.get("error_summary") or "; ".join(str(error) for error in errors[:3]) or "")
        trace.mark_finished(status=str(result.get("status") or ("failed" if errors else "success")))
        db: Session = SessionLocal()
        try:
            observations = dict(result.get("observations") or {})
            next_run_suggestions = self._build_next_run_suggestions(observations)
            self._remember_workflow_outcome(
                db,
                workflow_name=workflow_name,
                trace=trace,
                extra={
                    "node_count": len(graph_nodes),
                    "has_tool_stage": any(node.stage == "tool" for node in graph_nodes),
                    "observations": observations,
                    "reasoning_decisions": list(result.get("reasoning_decisions") or []),
                    "next_run_suggestions": next_run_suggestions,
                },
            )
        finally:
            db.close()
        return {
            **result,
            "run_id": resolved_run_id,
            "workflow_name": workflow_name,
            "source_name": source_name,
            "fetcher_name": fetcher_name,
            "processor_name": processor_name,
            "publisher_name": publisher_name,
            "lookback_hours": lookback_hours,
            "limit": limit,
            "options": resolved_options,
            "nodes": resolved_nodes,
        }

    def list_content_items(
        self,
        *,
        review_status: str | None = None,
        publish_status: str | None = None,
        pipeline_status: str | None = None,
        source_type: str | None = None,
        fetch_run_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._repository.list_items(
            ContentQuery(
                review_status=review_status,
                publish_status=publish_status,
                pipeline_status=pipeline_status,
                source_type=source_type,
                fetch_run_id=fetch_run_id,
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
