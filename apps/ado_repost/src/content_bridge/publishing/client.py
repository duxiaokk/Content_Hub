from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from urllib import error, request

from .config import PublishingSettings


@dataclass
class PublishResult:
    ok: bool
    status_code: int | None
    response_text: str


class BlogPublishingClient:
    def __init__(self, settings: PublishingSettings) -> None:
        self.settings = settings

    def publish_draft(self, payload: dict) -> PublishResult:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.settings.endpoint_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Internal-Token": self.settings.internal_token,
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return PublishResult(True, resp.status, text)
        except error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return PublishResult(False, exc.code, text)
        except Exception as exc:
            return PublishResult(False, None, str(exc))
