from __future__ import annotations

from workflow_engine.registry.contracts import ContentAsset, PublishResult, PublishTarget, Publisher


class BasePublisher(Publisher):
    name = "base"

    async def publish(self, content: ContentAsset, target: PublishTarget) -> PublishResult:
        raise NotImplementedError
