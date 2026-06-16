from __future__ import annotations

from typing import Any

from apps.platform.services.content_domain_contracts import ContentDomainResult


class ContentDomainClient:
    """B -> A 统一适配层。"""

    def __init__(self) -> None:
        self._workflow_service = None

    def _get_workflow_service(self):
        if self._workflow_service is None:
            from apps.workflow_engine.api.service import WorkflowEngineService

            self._workflow_service = WorkflowEngineService()
        return self._workflow_service

    async def run_content_radar(self, payload: dict[str, Any]) -> ContentDomainResult:
        result = await self._get_workflow_service().run_content_radar(payload)
        return ContentDomainResult(
            run_id=str(result.get("run_id") or payload.get("run_id") or ""),
            status="success" if not result.get("errors") else "partial",
            summary=f"prepared {len(result.get('review_items', []))} review items",
            errors=list(result.get("errors") or []),
            trace_ref=str(result.get("run_id") or payload.get("run_id") or ""),
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
            return ContentDomainResult(
                run_id=str(digest.run_id or payload.get("run_id") or ""),
                status="success",
                summary=f"digest generated with {digest.included_count} items",
                trace_ref=str(digest.run_id or payload.get("run_id") or ""),
                data=result,
            )
        finally:
            db.close()

    async def prepare_review_items(self, payload: dict[str, Any]) -> ContentDomainResult:
        result = await self.run_content_radar(payload)
        return ContentDomainResult(
            run_id=result.run_id,
            status=result.status,
            summary=result.summary,
            errors=result.errors,
            trace_ref=result.trace_ref,
            data={"review_items": result.data.get("review_items", [])},
        )

    async def publish_approved_content(self, payload: dict[str, Any]) -> ContentDomainResult:
        from sqlalchemy.orm import Session

        from apps.platform.database import SessionLocal
        from apps.platform.services.publish_service import PublishService

        content_item_id = int(payload["content_item_id"])
        db: Session = SessionLocal()
        try:
            result = PublishService(db).publish_blog_draft(
                content_item_id=content_item_id,
                run_id=str(payload.get("run_id") or "") or None,
            )
            status = "success" if result.get("status") in {"success", "skipped"} else "failed"
            return ContentDomainResult(
                run_id=str(payload.get("run_id") or f"blog-draft-{content_item_id}"),
                status=status,
                summary=str(result.get("message") or "publish completed"),
                trace_ref=str(payload.get("run_id") or f"blog-draft-{content_item_id}"),
                data=result,
            )
        finally:
            db.close()
