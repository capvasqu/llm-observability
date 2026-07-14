"""CallEvent — the system's central contract (PRD §5).

Every module (gateway, pricing, evaluating, reporting) speaks this language and only this.
Any breaking change to the schema requires bumping SCHEMA_VERSION.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

SCHEMA_VERSION = "1.0"

Outcome = Literal["ok", "error", "timeout"]
CostStatus = Literal["ok", "unknown_model", "unknown_tokens", "pending"]
Provider = Literal["anthropic", "openai"]


def utc_now_iso() -> str:
    """ISO-8601 timestamp in UTC with a Z suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class CallEvent:
    """A single measured LLM call."""

    # Identity
    provider: Provider
    endpoint: str
    outcome: Outcome
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = SCHEMA_VERSION
    ts_start: str = field(default_factory=utc_now_iso)
    ts_end: str = field(default_factory=utc_now_iso)

    # Context labels (from x-obs-* headers). Optional: they never block a call.
    project: str | None = None
    agent: str | None = None
    run_id: str | None = None
    tag: str | None = None

    # Model
    model: str | None = None
    streaming: bool = False

    # Consumption
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    # Cost (filled in by the pricing engine)
    cost: float | None = None
    currency: str | None = None
    cost_status: CostStatus = "pending"
    pricing_as_of: str | None = None

    # Performance
    ttfb_ms: int | None = None
    total_ms: int | None = None
    retries: int = 0

    # Result
    http_status: int | None = None
    error_type: str | None = None

    # Quality (optional, when an Evaluator is active)
    quality_score: float | None = None
    quality_detail: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.recompute_total_tokens()

    def recompute_total_tokens(self) -> None:
        """total_tokens is derived: it only exists when at least one side is known."""
        if self.input_tokens is None and self.output_tokens is None:
            self.total_tokens = None
        else:
            self.total_tokens = (self.input_tokens or 0) + (self.output_tokens or 0)

    @property
    def output_input_ratio(self) -> float | None:
        """Output/input ratio. Above 3x suggests the prompt is asking for too much text (RF-6.2)."""
        if not self.input_tokens or self.output_tokens is None:
            return None
        return self.output_tokens / self.input_tokens

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CallEvent:
        """Rebuild from a dict (a JSONL line or a SQLite row).

        Unknown keys are ignored so events written by a future schema version still load.
        """
        known = {f for f in cls.__dataclass_fields__}
        payload = {k: v for k, v in data.items() if k in known}
        event = cls(**payload)
        event.recompute_total_tokens()
        return event


def new_event(provider: Provider, endpoint: str, **kwargs: Any) -> CallEvent:
    """Create an in-flight event. `outcome` is finalized when the call closes."""
    kwargs.setdefault("outcome", "ok")
    return CallEvent(provider=provider, endpoint=endpoint, **kwargs)
