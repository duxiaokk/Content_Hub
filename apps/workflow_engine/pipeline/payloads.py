from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from workflow_engine.registry.contracts import FetchRequest, ProcessContext, PublishTarget


@dataclass(slots=True)
class LinearPipelinePayload:
    fetcher_name: str
    processor_name: str
    publisher_name: str
    fetch_request: FetchRequest
    process_context: ProcessContext
    publish_target: PublishTarget

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LinearPipelinePayload":
        fetch_request_raw = payload.get("fetch_request") or {}
        process_context_raw = payload.get("process_context") or {}
        publish_target_raw = payload.get("publish_target") or {}
        return cls(
            fetcher_name=str(payload.get("fetcher_name") or "cnblogs"),
            processor_name=str(payload.get("processor_name") or "rewrite"),
            publisher_name=str(payload.get("publisher_name") or "blog"),
            fetch_request=FetchRequest(
                source_name=str(fetch_request_raw.get("source_name") or payload.get("fetcher_name") or "cnblogs"),
                lookback_hours=int(fetch_request_raw.get("lookback_hours") or 24),
                limit=int(fetch_request_raw.get("limit") or 50),
                cursor=fetch_request_raw.get("cursor"),
                options=dict(fetch_request_raw.get("options") or {}),
            ),
            process_context=ProcessContext(
                run_id=process_context_raw.get("run_id"),
                options=dict(process_context_raw.get("options") or {}),
            ),
            publish_target=PublishTarget(
                target_name=str(publish_target_raw.get("target_name") or payload.get("publisher_name") or "blog"),
                options=dict(publish_target_raw.get("options") or {}),
            ),
        )
