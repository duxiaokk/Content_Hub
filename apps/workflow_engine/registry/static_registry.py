from __future__ import annotations

from apps.workflow_engine.registry.plugin_registry import PluginRegistry


registry = PluginRegistry()

RADAR_PIPELINE_STEPS = [
    {"name": "fetch", "handler": "fetcher_engine.FetchService.run_sources"},
    {"name": "dedup_filter", "handler": "workflow_engine.pipeline.filter_node.FilterNode.apply"},
    {"name": "summarize", "handler": "ai_processor.processors.summarize.SummarizeProcessor.process"},
    {"name": "classify_tag", "handler": "ai_processor.processors.classify.ClassifyProcessor.process"},
    {"name": "rewrite", "handler": "ai_processor.processors.rewrite.RewriteProcessor.process"},
    {"name": "review_prepare", "handler": "platform.services.review_service.prepare_review_queue"},
]
