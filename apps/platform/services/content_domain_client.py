from __future__ import annotations

from typing import Any

from apps.platform.services.content_domain_contracts import ContentDomainResult


class UnsupportedPublishTargetError(ValueError):
    pass


class ContentDomainClient:
    """B -> A 统一适配层。"""

    def __init__(self) -> None:
        self._workflow_service = None

    def _get_workflow_service(self):
        if self._workflow_service is None:
            from apps.workflow_engine.api.service import WorkflowEngineService

            self._workflow_service = WorkflowEngineService()
        return self._workflow_service

    @staticmethod
    def _build_result(
        *,
        run_id: str,
        status: str,
        summary: str,
        data: dict[str, Any],
        errors: list[dict[str, Any]] | None = None,
        trace_ref: str | None = None,
    ) -> ContentDomainResult:
        return ContentDomainResult(
            run_id=run_id,
            status=status,
            summary=summary,
            errors=list(errors or []),
            trace_ref=trace_ref or run_id,
            data=data,
        )

    async def run_content_radar(self, payload: dict[str, Any]) -> ContentDomainResult:
        result = await self._get_workflow_service().run_content_radar(payload)
        errors = list(result.get("errors") or [])
        run_id = str(result.get("run_id") or payload.get("run_id") or "")
        return self._build_result(
            run_id=run_id,
            status="partial" if errors else "success",
            summary=f"prepared {len(result.get('review_items', []))} review items",
            errors=errors,
            trace_ref=run_id,
            data=result,
        )

    async def run_content_workflow(self, payload: dict[str, Any]) -> ContentDomainResult:
        result = await self._get_workflow_service().run_content_workflow(
            workflow_name=str(payload.get("workflow_name") or "content.workflow.run"),
            source_name=str(payload.get("source_name") or payload.get("fetcher_name") or "cnblogs"),
            fetcher_name=str(payload.get("fetcher_name") or "cnblogs"),
            processor_name=str(payload.get("processor_name") or "rewrite"),
            publisher_name=str(payload.get("publisher_name") or "blog"),
            lookback_hours=int(payload.get("lookback_hours") or 24),
            limit=int(payload.get("limit") or 20),
            options={
                "fetch": dict(payload.get("fetch_options") or {}),
                "process": dict(payload.get("process_options") or {}),
                "publish": dict(payload.get("publish_options") or {}),
            },
            nodes=list(payload.get("nodes") or []),
            run_id=str(payload.get("run_id") or ""),
        )
        run_id = str(result.get("run_id") or payload.get("run_id") or "")
        workflow_status = str(result.get("status") or "").strip().lower()
        status = "success"
        errors: list[dict[str, Any]] = []
        if workflow_status == "partial":
            status = "partial"
            errors.append(
                {
                    "workflow_name": str(result.get("workflow_name") or payload.get("workflow_name") or "content.workflow.run"),
                    "status": workflow_status,
                }
            )
        elif workflow_status not in {"", "succeeded", "success"}:
            status = "failed"
            errors.append(
                {
                    "workflow_name": str(result.get("workflow_name") or payload.get("workflow_name") or "content.workflow.run"),
                    "status": workflow_status or "failed",
                }
            )
        return self._build_result(
            run_id=run_id,
            status=status,
            summary=f"workflow {result.get('workflow_name') or 'content.workflow.run'} completed",
            errors=errors,
            trace_ref=run_id,
            data=result,
        )

    async def run_daily_digest(self, payload: dict[str, Any]) -> ContentDomainResult:
        from sqlalchemy.orm import Session

        from apps.platform.database import SessionLocal
        from apps.platform.services.digest_service import DigestService

        db: Session = SessionLocal()
        try:
            digest = DigestService(db).generate_digest(
                run_id=str(payload.get("run_id") or "") or None,
                lookback_hours=int(payload.get("lookback_hours") or 24),
            )
            result = {
                "id": int(digest.id),
                "title": digest.title,
                "included_count": int(digest.included_count),
                "run_id": digest.run_id,
            }
            run_id = str(digest.run_id or payload.get("run_id") or "")
            return self._build_result(
                run_id=run_id,
                status="success",
                summary=f"digest generated with {digest.included_count} items",
                trace_ref=run_id,
                data=result,
            )
        finally:
            db.close()

    async def prepare_review_items(self, payload: dict[str, Any]) -> ContentDomainResult:
        result = await self.run_content_radar(payload)
        return self._build_result(
            run_id=result.run_id,
            status=result.status,
            summary=result.summary or "prepared review items",
            errors=result.errors,
            trace_ref=result.trace_ref,
            data={"review_items": result.data.get("review_items", [])},
        )

    async def publish_approved_content(self, payload: dict[str, Any]) -> ContentDomainResult:
        from sqlalchemy.orm import Session

        from apps.platform.database import SessionLocal
        from apps.platform.services.publish_service import PublishService

        content_item_id = int(payload["content_item_id"])
        target_type = str(payload.get("target_type") or "blog").strip().lower()
        if target_type != "blog":
            raise UnsupportedPublishTargetError(f"unsupported publish target_type: {target_type}")
        db: Session = SessionLocal()
        try:
            result = PublishService(db).publish_blog_draft(
                content_item_id=content_item_id,
                run_id=str(payload.get("run_id") or "") or None,
            )
            status = "success" if result.get("status") in {"success", "skipped"} else "failed"
            run_id = str(payload.get("run_id") or f"blog-draft-{content_item_id}")
            errors = []
            if status == "failed":
                errors.append(
                    {
                        "content_item_id": content_item_id,
                        "target_type": target_type,
                        "message": str(result.get("message") or "publish failed"),
                    }
                )
            return self._build_result(
                run_id=run_id,
                status=status,
                summary=str(result.get("message") or "publish completed"),
                errors=errors,
                trace_ref=run_id,
                data=result,
            )
        finally:
            db.close()
