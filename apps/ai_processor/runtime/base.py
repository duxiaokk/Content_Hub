from __future__ import annotations

from apps.workflow_engine.registry.contracts import (
    AIProcessorConfig,
    ContentAsset,
    ProcessContext,
    ProcessResult,
    Processor,
)


class BaseProcessor(Processor):
    name = "base"

    def __init__(self, config: AIProcessorConfig) -> None:
        self.config = config

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        raise NotImplementedError
