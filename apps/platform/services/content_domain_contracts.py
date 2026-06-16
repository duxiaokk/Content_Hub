from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ContentDomainResult:
    run_id: str
    status: str
    summary: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    trace_ref: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
