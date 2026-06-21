from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from agents.base_agent import AgentConfig
from agents.tool_calling_agent import ToolCallingAgent
from apps.platform.models import ContentItem, ReviewQueue
from apps.platform.schemas.review import ReviewApproveRequest, ReviewQueueOut, ReviewRejectRequest
from apps.platform.services.agent_memory_service import AgentMemoryService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReviewNotFoundError(ValueError):
    pass


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_pending_reviews(self, page: int, page_size: int, status: str = "pending") -> tuple[list[dict], int]:
        try:
            query = (
                self.db.query(ReviewQueue, ContentItem)
                .join(ContentItem, ContentItem.id == ReviewQueue.content_item_id)
                .filter(ReviewQueue.status == status)
                .order_by(ReviewQueue.created_at.asc(), ReviewQueue.id.asc())
            )
            total = query.count()
            rows = query.offset((page - 1) * page_size).limit(page_size).all()
        except OperationalError:
            return [], 0
        return [self._serialize_review(review, item) for review, item in rows], total

    def get_review_detail(self, review_id: int) -> dict:
        row = (
            self.db.query(ReviewQueue, ContentItem)
            .join(ContentItem, ContentItem.id == ReviewQueue.content_item_id)
            .filter(ReviewQueue.id == review_id)
            .first()
        )
        if row is None:
            raise ReviewNotFoundError(f"review not found: {review_id}")
        review, item = row
        return self._serialize_review(review, item)

    def approve(self, review_id: int, data: ReviewApproveRequest) -> dict:
        review, item = self._load_review_with_item(review_id)
        now = _utcnow()

        if data.edited_title is not None:
            review.candidate_title = data.edited_title
            item.rewritten_title = data.edited_title
        if data.edited_content is not None:
            review.candidate_content = data.edited_content
            item.rewritten_content = data.edited_content

        review.status = "approved"
        review.reviewer = data.reviewer
        review.reviewed_at = now

        item.review_status = "approved"
        item.reviewed_by = data.reviewer
        item.reviewed_at = now

        self.db.add(review)
        self.db.add(item)
        self.db.commit()
        self._record_review_memory(
            item=item,
            decision="approved",
            reviewer=data.reviewer,
            note=review.review_note,
            metadata={
                "review_id": int(review.id),
                "edited_title": review.candidate_title,
                "edited_content": review.candidate_content,
            },
        )
        self.db.refresh(review)
        self.db.refresh(item)
        return self._serialize_review(review, item)

    def reject(self, review_id: int, data: ReviewRejectRequest) -> dict:
        review, item = self._load_review_with_item(review_id)
        now = _utcnow()

        review.status = "rejected"
        review.reviewer = data.reviewer
        review.review_note = data.note
        review.reviewed_at = now

        item.review_status = "rejected"
        item.reviewed_by = data.reviewer
        item.reviewed_at = now

        self.db.add(review)
        self.db.add(item)
        self.db.commit()
        self._record_review_memory(
            item=item,
            decision="rejected",
            reviewer=data.reviewer,
            note=data.note,
            metadata={"review_id": int(review.id)},
        )
        self.db.refresh(review)
        self.db.refresh(item)
        return self._serialize_review(review, item)

    def archive(self, review_id: int, reviewer: str) -> dict:
        review, item = self._load_review_with_item(review_id)
        now = _utcnow()

        review.status = "archived"
        review.reviewer = reviewer
        review.reviewed_at = now

        item.review_status = "archived"
        item.reviewed_by = reviewer
        item.reviewed_at = now

        self.db.add(review)
        self.db.add(item)
        self.db.commit()
        self._record_review_memory(
            item=item,
            decision="archived",
            reviewer=reviewer,
            note=review.review_note,
            metadata={"review_id": int(review.id)},
        )
        self.db.refresh(review)
        self.db.refresh(item)
        return self._serialize_review(review, item)

    def auto_review(
        self,
        review_id: int,
        *,
        reviewer: str = "quality-gate",
        use_tool: bool = False,
        auto_approve: bool = False,
        auto_reject: bool = True,
    ) -> dict:
        review, item = self._load_review_with_item(review_id)
        now = _utcnow()
        gate = self._build_quality_gate(review, item, use_tool=use_tool)
        metadata = self._load_item_metadata(item)
        metadata["quality_gate"] = gate
        item.metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)

        review.reviewer = reviewer
        review.review_note = gate["summary"]
        if gate["status"] == "failed" and auto_reject:
            review.status = "rejected"
            review.reviewed_at = now
            item.review_status = "rejected"
            item.reviewed_by = reviewer
            item.reviewed_at = now
        elif gate["status"] == "passed" and auto_approve:
            review.status = "approved"
            review.reviewed_at = now
            item.review_status = "approved"
            item.reviewed_by = reviewer
            item.reviewed_at = now
        else:
            review.status = "pending"
            review.reviewed_at = None

        self.db.add(review)
        self.db.add(item)
        self.db.commit()
        self._record_review_memory(
            item=item,
            decision=review.status,
            reviewer=reviewer,
            note=review.review_note,
            metadata={
                "review_id": int(review.id),
                "quality_gate": gate,
            },
        )
        self.db.refresh(review)
        self.db.refresh(item)
        return self._serialize_review(review, item)

    def _load_review_with_item(self, review_id: int) -> tuple[ReviewQueue, ContentItem]:
        row = (
            self.db.query(ReviewQueue, ContentItem)
            .join(ContentItem, ContentItem.id == ReviewQueue.content_item_id)
            .filter(ReviewQueue.id == review_id)
            .first()
        )
        if row is None:
            raise ReviewNotFoundError(f"review not found: {review_id}")
        return row

    def _serialize_review(self, review: ReviewQueue, item: ContentItem) -> dict:
        tags: list[str] | None
        try:
            tags = json.loads(item.tags_json or "[]")
        except json.JSONDecodeError:
            tags = []
        metadata = self._load_item_metadata(item)
        payload = ReviewQueueOut(
            id=int(review.id),
            content_item_id=int(review.content_item_id),
            candidate_title=review.candidate_title,
            candidate_content=review.candidate_content,
            status=review.status,
            reviewer=review.reviewer,
            review_note=review.review_note,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            original_title=item.title,
            original_content=item.raw_content,
            summary=item.summary,
            score=float(item.score) if item.score is not None else None,
            tags=tags,
            source_url=item.source_url,
            publish_status=item.publish_status,
            publish_path=f"/console/content-items/{item.id}/publish-to-post" if review.status == "approved" else None,
            next_action="publish_to_post" if review.status == "approved" else None,
            quality_gate=metadata.get("quality_gate") if isinstance(metadata.get("quality_gate"), dict) else None,
        )
        return payload.model_dump(mode="json")

    @staticmethod
    def _load_item_metadata(item: ContentItem) -> dict[str, Any]:
        try:
            parsed = json.loads(item.metadata_json or "{}")
        except json.JSONDecodeError:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}

    def _build_quality_gate(self, review: ReviewQueue, item: ContentItem, *, use_tool: bool) -> dict[str, Any]:
        candidate_title = self._resolve_candidate_text(review.candidate_title, item.rewritten_title)
        candidate_content = self._resolve_candidate_text(review.candidate_content, item.rewritten_content)
        original_content = str(item.raw_content or "").strip()
        original_title = str(item.title or "").strip()
        metadata = self._load_item_metadata(item)
        self_critique_score = self._extract_self_critique_score(metadata)
        tool_result: dict[str, Any] | None = None

        checks: list[dict[str, Any]] = [
            {
                "name": "has_title",
                "passed": bool(candidate_title),
                "detail": "candidate title exists",
            },
            {
                "name": "has_content",
                "passed": bool(candidate_content),
                "detail": "candidate content exists",
            },
            {
                "name": "content_length",
                "passed": self._passes_length_check(candidate_content, original_content),
                "detail": "candidate content keeps enough length",
            },
            {
                "name": "source_traceable",
                "passed": bool(item.source_url or original_title),
                "detail": "source or original title can be traced",
            },
            {
                "name": "rewrite_quality",
                "passed": self_critique_score is None or self_critique_score >= 0.6,
                "detail": "self critique score meets threshold",
            },
        ]

        if use_tool:
            tool_result = self._run_tool_fact_check(candidate_title or original_title or item.source_url or "")
            checks.append(
                {
                    "name": "tool_fact_check",
                    "passed": bool(tool_result.get("success")) and bool(tool_result.get("result", {}).get("results")),
                    "detail": tool_result.get("summary") or "tool fact check finished",
                }
            )

        passed_checks = sum(1 for check in checks if check["passed"])
        score = round(passed_checks / max(len(checks), 1), 2)
        if score >= 0.8:
            status = "passed"
        elif score < 0.5:
            status = "failed"
        else:
            status = "pending"

        failed_names = [check["name"] for check in checks if not check["passed"]]
        summary = (
            f"quality_gate:{status}; score={score}; failed={','.join(failed_names) or 'none'}"
        )
        result = {
            "status": status,
            "score": score,
            "checks": checks,
            "summary": summary,
        }
        if self_critique_score is not None:
            result["self_critique_score"] = self_critique_score
        if tool_result is not None:
            result["tool_result"] = tool_result
        return result

    def _record_review_memory(
        self,
        *,
        item: ContentItem,
        decision: str,
        reviewer: str,
        note: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        AgentMemoryService(self.db).record_review_feedback(
            content_item_id=int(item.id),
            decision=decision,
            reviewer=reviewer,
            note=note,
            source_url=item.source_url,
            workflow_name=self._extract_workflow_name(item),
            metadata=metadata,
        )

    @staticmethod
    def _extract_workflow_name(item: ContentItem) -> str | None:
        metadata = ReviewService._load_item_metadata(item)
        workflow_name = metadata.get("workflow_name")
        if workflow_name is None and isinstance(metadata.get("workflow"), dict):
            workflow_name = metadata["workflow"].get("name")
        if workflow_name is None:
            return None
        resolved = str(workflow_name).strip()
        return resolved or None

    @staticmethod
    def _resolve_candidate_text(review_value: str | None, fallback_value: str | None) -> str:
        if review_value is not None:
            return str(review_value).strip()
        return str(fallback_value or "").strip()

    @staticmethod
    def _passes_length_check(candidate_content: str, original_content: str) -> bool:
        if not candidate_content:
            return False
        if len(candidate_content) >= 80:
            return True
        if not original_content:
            return len(candidate_content) >= 20
        return (len(candidate_content) / max(len(original_content), 1)) >= 0.2

    @staticmethod
    def _extract_self_critique_score(metadata: dict[str, Any]) -> float | None:
        score = metadata.get("self_critique_score")
        if score is None and isinstance(metadata.get("rewrite"), dict):
            score = metadata["rewrite"].get("self_critique_score")
        if score is None:
            return None
        try:
            return float(score)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _run_tool_fact_check(query: str) -> dict[str, Any]:
        if not query:
            return {"success": False, "summary": "missing query"}
        agent = ToolCallingAgent(
            AgentConfig(
                agent_key="tool-calling-agent",
                task_types=["tool.execute"],
                mock_llm=True,
            )
        )
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            has_running_loop = False
        else:
            has_running_loop = True

        if has_running_loop:
            result = {
                "results": [agent._tool_web_search({"query": query})],  # noqa: SLF001
                "summary": "1/1 tools succeeded",
            }
        else:
            result = asyncio.run(
                agent.execute(
                    "tool.execute",
                    {
                        "tool_calls": [
                            {
                                "tool_name": "web_search",
                                "parameters": {"query": query},
                            }
                        ]
                    },
                    None,
                )
            )
        first = result.get("results", [{}])[0] if isinstance(result.get("results"), list) and result.get("results") else {}
        return {
            "success": bool(first.get("success")),
            "summary": str(result.get("summary") or ""),
            "result": dict(first.get("result") or {}),
        }
