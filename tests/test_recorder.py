"""M2 — persistence: JSONL (truth) + SQLite (queries), and the robustness invariant."""

import json

import pytest

from llmobs.recording import CallEvent, EventStore, Recorder, new_event


@pytest.fixture
def recorder(tmp_path):
    with Recorder(tmp_path) as r:
        yield r


def _sample(**kw) -> CallEvent:
    base = dict(
        model="claude-opus-4-8",
        project="p8-agents",
        agent="estimation_agent",
        input_tokens=1520,
        output_tokens=640,
        cost=0.0672,
        currency="USD",
        cost_status="ok",
        ttfb_ms=380,
        total_ms=1240,
        http_status=200,
    )
    base.update(kw)
    return new_event("anthropic", "/v1/messages", **base)


def test_record_persists_and_reads_back_from_sqlite(recorder):
    event = _sample()
    assert recorder.record(event) is True

    back = recorder.store.get(event.id)
    assert back is not None
    assert back == event
    assert back.total_tokens == 2160
    assert back.cost == pytest.approx(0.0672)


def test_record_writes_one_jsonl_line_per_event(recorder):
    recorder.record(_sample())
    recorder.record(_sample(agent="report_agent"))

    lines = recorder.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["agent"] == "report_agent"


def test_sqlite_can_be_rebuilt_from_jsonl(recorder, tmp_path):
    """The JSONL is the source of truth: delete the database and it comes back whole."""
    events = [_sample(agent=f"agent_{i}") for i in range(3)]
    for e in events:
        recorder.record(e)

    with EventStore(tmp_path / "rebuilt.db") as fresh:
        assert fresh.count() == 0
        n = fresh.rebuild_from_jsonl(recorder.jsonl_path)
        assert n == 3
        assert [e.agent for e in fresh.all()] == ["agent_0", "agent_1", "agent_2"]


def test_reinserting_the_same_id_does_not_duplicate(recorder):
    event = _sample()
    recorder.record(event)
    recorder.record(event)
    assert recorder.store.count() == 1


def test_optional_fields_travel_as_null(recorder):
    """Without x-obs-* headers the label fields stay null and block nothing (RF-3.3)."""
    event = new_event("openai", "/v1/chat/completions", model="gpt-4o")
    recorder.record(event)

    back = recorder.store.get(event.id)
    assert back.project is None and back.agent is None and back.run_id is None
    assert back.total_tokens is None


def test_quality_detail_survives_the_roundtrip(recorder):
    event = _sample(quality_score=1.0, quality_detail={"json_valid": True, "fields_complete": 1.0})
    recorder.record(event)

    back = recorder.store.get(event.id)
    assert back.quality_detail == {"json_valid": True, "fields_complete": 1.0}


def test_persistence_failure_does_not_raise_to_the_caller(recorder, monkeypatch):
    """INVARIANT RNF-4: if observability fails, the client never finds out."""
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(recorder.store, "insert", boom)

    ok = recorder.record(_sample())  # must not raise

    assert ok is False
    assert recorder.failures == 1


def test_a_corrupt_jsonl_line_does_not_abort_the_read(recorder, tmp_path):
    recorder.record(_sample(agent="good_1"))
    with recorder.jsonl_path.open("a", encoding="utf-8") as fh:
        fh.write("{this is not json}\n")
    recorder.record(_sample(agent="good_2"))

    with EventStore(tmp_path / "rebuilt.db") as fresh:
        assert fresh.rebuild_from_jsonl(recorder.jsonl_path) == 2
        assert [e.agent for e in fresh.all()] == ["good_1", "good_2"]
