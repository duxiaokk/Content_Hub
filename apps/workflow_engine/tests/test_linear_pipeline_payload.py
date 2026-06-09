from __future__ import annotations

from workflow_engine.pipeline.payloads import LinearPipelinePayload


def test_linear_pipeline_payload_from_dict() -> None:
    payload = LinearPipelinePayload.from_dict(
        {
            "fetcher_name": "cnblogs",
            "processor_name": "rewrite",
            "publisher_name": "blog",
            "fetch_request": {"source_name": "cnblogs", "lookback_hours": 12, "limit": 5},
            "process_context": {"run_id": "run-1", "options": {"tone": "technical"}},
            "publish_target": {"target_name": "blog", "options": {"tags": ["python"]}},
        }
    )

    assert payload.fetcher_name == "cnblogs"
    assert payload.fetch_request.lookback_hours == 12
    assert payload.process_context.run_id == "run-1"
    assert payload.publish_target.target_name == "blog"
