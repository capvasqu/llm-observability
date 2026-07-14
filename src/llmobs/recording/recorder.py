"""Recorder — persists every CallEvent to JSONL (source of truth) + SQLite (query index).

ROBUSTNESS INVARIANT (RNF-4 / spec §2.4): a failure here must NEVER propagate to the
caller. Observability is a passive observer: if it cannot measure, the client still gets
its response. Failures are counted and logged separately.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from llmobs.recording.event import CallEvent
from llmobs.recording.store import EventStore

log = logging.getLogger("llmobs.recording")


class Recorder:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.data_dir / "events.jsonl"
        self.store = EventStore(self.data_dir / "llmobs.db")
        self.failures = 0
        self._lock = threading.Lock()

    def record(self, event: CallEvent) -> bool:
        """Persist the event. Returns True if stored, False if it failed.

        Never raises: an observability failure must not bring down the client's call.
        """
        try:
            with self._lock:
                self._append_jsonl(event)
                self.store.insert(event)
            return True
        except Exception:  # noqa: BLE001 — invariant: swallow everything, but leave a trace
            with self._lock:
                self.failures += 1
            log.exception(
                "failed to record CallEvent id=%s (the client's call is unaffected)", event.id
            )
            return False

    def _append_jsonl(self, event: CallEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> Recorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
