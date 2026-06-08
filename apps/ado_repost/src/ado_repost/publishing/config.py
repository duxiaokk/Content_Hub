from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class PublishingSettings:
    enabled: bool = False
    endpoint_url: str = "http://127.0.0.1:8000/api/internal/agent/drafts"
    internal_token: str = "local-dev-internal-token"
    timeout_seconds: float = 15.0
    source_platform: str = "youtube"


def load_publishing_settings() -> PublishingSettings:
    return PublishingSettings(
        enabled=os.environ.get("ADO_PUBLISH_ENABLED", "false").lower() in {"1", "true", "yes"},
        endpoint_url=os.environ.get(
            "ADO_PUBLISH_ENDPOINT_URL",
            "http://127.0.0.1:8000/api/internal/agent/drafts",
        ),
        internal_token=os.environ.get("ADO_INTERNAL_TOKEN", "local-dev-internal-token"),
        timeout_seconds=float(os.environ.get("ADO_PUBLISH_TIMEOUT_SECONDS", "15")),
        source_platform=os.environ.get("ADO_SOURCE_PLATFORM", "youtube"),
    )
