from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_CONTENT_DOMAIN_STATUS = {"success", "partial", "failed"}


@dataclass(slots=True)
class ContentDomainResult:
    run_id: str
    status: str
    summary: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    trace_ref: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_CONTENT_DOMAIN_STATUS:
            raise ValueError(f"invalid content domain status: {self.status}")
        if self.status == "success" and self.errors:
            raise ValueError("success result must not contain errors")
        if self.status == "failed" and not self.errors:
            raise ValueError("failed result must contain errors")
        if self.trace_ref is None:
            self.trace_ref = self.run_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
