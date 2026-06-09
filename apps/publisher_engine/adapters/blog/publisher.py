from __future__ import annotations

from publisher_engine.runtime.base import BasePublisher
from publisher_engine.runtime.settings import PublisherSettings
from workflow_engine.runtime.legacy_paths import ensure_legacy_paths
from workflow_engine.registry.contracts import ContentAsset, PublishResult, PublishTarget

ensure_legacy_paths()

from ado_repost.publishing.client import BlogPublishingClient
from ado_repost.publishing.config import PublishingSettings
from ado_repost.publishing.models import DraftPayload


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

        publishing_settings = PublishingSettings(
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
