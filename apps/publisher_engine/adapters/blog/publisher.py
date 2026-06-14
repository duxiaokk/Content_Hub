from __future__ import annotations

from apps.publisher_engine.runtime.base import BasePublisher
from apps.publisher_engine.runtime.client import BlogPublishingClient
from apps.publisher_engine.runtime.models import DraftPayload, PublishRequest, PublishResponse
from apps.publisher_engine.runtime.settings import PublisherSettings
from apps.workflow_engine.registry.contracts import ContentAsset, PublishResult, PublishTarget


class BlogPublisher(BasePublisher):
    name = "blog"

    def __init__(self) -> None:
        self.settings = PublisherSettings()

    async def publish(self, content: ContentAsset, target: PublishTarget) -> PublishResult:
        if not self.settings.enabled:
            return PublishResult(
                status="disabled",
                target_name=target.target_name,
                error_message="publisher disabled by configuration",
            )

        publishing_settings = PublisherSettings(
            enabled=self.settings.enabled,
            endpoint_url=target.options.get("endpoint_url", self.settings.endpoint_url),
            internal_token=target.options.get("internal_token", self.settings.internal_token),
            timeout_seconds=float(target.options.get("timeout_seconds", self.settings.timeout_seconds)),
            source_platform=target.options.get("source_platform", self.settings.source_platform),
        )
        client = BlogPublishingClient(publishing_settings)
        payload = DraftPayload(
            title=content.title,
            summary=(content.raw_content or "")[:240] or None,
            markdown_content=content.processed_content or content.raw_content or "",
            source_platform=publishing_settings.source_platform,
            source_link=content.source_url or "",
            source_external_id=content.source_id,
            source_dedup_key=f"{content.source_type}:{content.source_id}",
            tags=list(target.options.get("tags", [])),
            raw_payload=dict(content.metadata),
        )
        result = client.publish_draft(payload.to_dict())
        return PublishResult(
            status="published" if result.ok else "failed",
            target_name=target.target_name,
            external_id=None,
            url=None,
            error_message=None if result.ok else result.response_text,
            metadata={
                "status_code": result.status_code,
                "response_text": result.response_text,
                "endpoint_url": publishing_settings.endpoint_url,
            },
        )

    async def publish_draft(self, request: PublishRequest) -> PublishResponse:
        content = ContentAsset(
            content_id=request.content_item_id,
            source_type=str(request.options.get("source_type", "content_hub")),
            source_id=str(request.options.get("source_id", request.content_item_id)),
            title=request.candidate_title,
            raw_content=request.candidate_content,
            processed_content=request.candidate_content,
            source_url=request.source_url,
            metadata={"tags": list(request.tags)},
        )
        target = PublishTarget(
            target_name="blog",
            options={
                **dict(request.options),
                "mode": str(request.options.get("mode", "draft")),
                "tags": list(request.tags),
            },
        )
        result = await self.publish(content, target)
        return PublishResponse(
            content_item_id=request.content_item_id,
            target_type=request.target_type,
            status="success" if result.status == "published" else "failed",
            external_url=result.url,
            external_id=result.external_id,
            message=result.error_message or result.status,
        )
