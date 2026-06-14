from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request

from apps.publisher_engine.runtime.settings import PublisherSettings


@dataclass(slots=True)
class ClientPublishResult:
    ok: bool
    status_code: int | None
    response_text: str


class BlogPublishingClient:
    def __init__(self, settings: PublisherSettings) -> None:
        self.settings = settings

    def publish_draft(self, payload: dict) -> ClientPublishResult:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        publish_request = request.Request(
            self.settings.endpoint_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Internal-Token": self.settings.internal_token,
            },
        )
        try:
            with request.urlopen(publish_request, timeout=self.settings.timeout_seconds) as response:
                text = response.read().decode("utf-8", errors="replace")
                return ClientPublishResult(ok=True, status_code=response.status, response_text=text)
        except error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return ClientPublishResult(ok=False, status_code=exc.code, response_text=text)
        except Exception as exc:
            return ClientPublishResult(ok=False, status_code=None, response_text=str(exc))
