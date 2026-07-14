"""llmobs configuration.

Precedence (spec §9): explicit overrides (CLI flags) > environment variables > defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_PORT = 8900
DEFAULT_DATA_DIR = "./data"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com"
DEFAULT_PRICING_FILE = "./pricing.yaml"

_TRUTHY = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


@dataclass(frozen=True)
class Config:
    port: int = DEFAULT_PORT
    data_dir: Path = Path(DEFAULT_DATA_DIR)
    anthropic_base_url: str = DEFAULT_ANTHROPIC_BASE_URL
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    pricing_file: Path = Path(DEFAULT_PRICING_FILE)
    capture_bodies: bool = False
    """Opt-in: store prompt/response bodies. Off by default (RF-5.3, privacy)."""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "llmobs.db"

    @property
    def jsonl_path(self) -> Path:
        return self.data_dir / "events.jsonl"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @classmethod
    def load(cls, **overrides: object) -> Config:
        """Build the config: defaults < environment < overrides (None values are ignored)."""
        base = cls(
            port=int(os.environ.get("LLMOBS_PORT", DEFAULT_PORT)),
            data_dir=Path(os.environ.get("LLMOBS_DATA_DIR", DEFAULT_DATA_DIR)),
            anthropic_base_url=os.environ.get(
                "ANTHROPIC_BASE_URL", DEFAULT_ANTHROPIC_BASE_URL
            ).rstrip("/"),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/"),
            pricing_file=Path(os.environ.get("LLMOBS_PRICING_FILE", DEFAULT_PRICING_FILE)),
            capture_bodies=_env_bool("LLMOBS_CAPTURE_BODIES", False),
        )
        applied = {k: v for k, v in overrides.items() if v is not None}
        if not applied:
            return base

        if "data_dir" in applied:
            applied["data_dir"] = Path(str(applied["data_dir"]))
        if "pricing_file" in applied:
            applied["pricing_file"] = Path(str(applied["pricing_file"]))
        for url_key in ("anthropic_base_url", "openai_base_url"):
            if url_key in applied:
                applied[url_key] = str(applied[url_key]).rstrip("/")

        return replace(base, **applied)  # type: ignore[arg-type]
