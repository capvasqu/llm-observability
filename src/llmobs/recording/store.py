"""EventStore — SQLite persistence for CallEvent (spec §5.1).

SQLite is the query index. The portable source of truth is the JSONL: this database can
always be rebuilt from it (`rebuild_from_jsonl`).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from llmobs.recording.event import CallEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS call_events (
  id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  ts_start TEXT NOT NULL,
  ts_end   TEXT NOT NULL,
  project TEXT, agent TEXT, run_id TEXT, tag TEXT,
  provider TEXT NOT NULL, endpoint TEXT NOT NULL,
  model TEXT, streaming INTEGER,
  input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
  cost REAL, currency TEXT, cost_status TEXT, pricing_as_of TEXT,
  ttfb_ms INTEGER, total_ms INTEGER, retries INTEGER,
  outcome TEXT NOT NULL, http_status INTEGER, error_type TEXT,
  quality_score REAL, quality_detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_ts ON call_events(ts_start);
CREATE INDEX IF NOT EXISTS idx_project_agent ON call_events(project, agent);
CREATE INDEX IF NOT EXISTS idx_model ON call_events(model);
"""

# INSERT column order. `quality_detail` travels as JSON (TEXT).
_COLUMNS = [
    "id", "schema_version", "ts_start", "ts_end",
    "project", "agent", "run_id", "tag",
    "provider", "endpoint", "model", "streaming",
    "input_tokens", "output_tokens", "total_tokens",
    "cost", "currency", "cost_status", "pricing_as_of",
    "ttfb_ms", "total_ms", "retries",
    "outcome", "http_status", "error_type",
    "quality_score", "quality_detail",
]


def _to_row(event: CallEvent) -> list[Any]:
    data = event.to_dict()
    data["streaming"] = int(bool(data["streaming"]))
    detail = data.get("quality_detail")
    data["quality_detail"] = json.dumps(detail) if detail is not None else None
    return [data[c] for c in _COLUMNS]


def _from_row(row: sqlite3.Row) -> CallEvent:
    data = dict(row)
    data["streaming"] = bool(data["streaming"])
    if data.get("quality_detail"):
        data["quality_detail"] = json.loads(data["quality_detail"])
    return CallEvent.from_dict(data)


class EventStore:
    """SQLite access to CallEvents. Idempotent by `id` (re-inserting does not duplicate)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def insert(self, event: CallEvent) -> None:
        placeholders = ", ".join("?" for _ in _COLUMNS)
        columns = ", ".join(_COLUMNS)
        self._conn.execute(
            f"INSERT OR REPLACE INTO call_events ({columns}) VALUES ({placeholders})",
            _to_row(event),
        )
        self._conn.commit()

    def get(self, event_id: str) -> CallEvent | None:
        row = self._conn.execute(
            "SELECT * FROM call_events WHERE id = ?", (event_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def all(self) -> list[CallEvent]:
        rows = self._conn.execute("SELECT * FROM call_events ORDER BY ts_start").fetchall()
        return [_from_row(r) for r in rows]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM call_events").fetchone()[0])

    def rebuild_from_jsonl(self, jsonl_path: Path) -> int:
        """Rebuild the database from the JSONL (the source of truth). Returns the event count."""
        self._conn.execute("DELETE FROM call_events")
        self._conn.commit()
        n = 0
        for event in read_jsonl(jsonl_path):
            self.insert(event)
            n += 1
        return n

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_jsonl(jsonl_path: Path) -> Iterator[CallEvent]:
    """Read the append-only JSONL. One corrupt line does not abort reading the rest."""
    path = Path(jsonl_path)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield CallEvent.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
