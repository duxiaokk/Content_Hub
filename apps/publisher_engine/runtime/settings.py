from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class PublisherSettings:
    enabled: bool = os.getenv("ADO_PUBLISH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    endpoint_url: str = os.getenv(
        "ADO_PUBLISH_ENDPOINT_URL",
        "http://127.0.0.1:8000/api/internal/agent/drafts",
    )
    internal_token: str = os.getenv("ADO_INTERNAL_TOKEN", "local-dev-internal-token")
    timeout_seconds: float = float(os.getenv("ADO_PUBLISH_TIMEOUT_SECONDS", "15"))
    source_platform: str = os.getenv("ADO_SOURCE_PLATFORM", "cnblogs")
    digest_output_dir: str = os.getenv("CONTENT_HUB_DIGEST_OUTPUT_DIR", ".tmp/digests")
