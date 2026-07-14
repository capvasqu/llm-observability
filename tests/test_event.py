"""M2 — the CallEvent contract."""

from llmobs.recording import SCHEMA_VERSION, CallEvent, new_event


def test_new_event_has_identity_and_schema():
    e = new_event("anthropic", "/v1/messages")
    assert e.id
    assert e.schema_version == SCHEMA_VERSION
    assert e.ts_start.endswith("Z")
    assert e.outcome == "ok"
    assert e.cost_status == "pending"


def test_total_tokens_is_derived():
    e = new_event("anthropic", "/v1/messages", input_tokens=1520, output_tokens=640)
    assert e.total_tokens == 2160


def test_total_tokens_is_none_when_usage_is_unknown():
    """With no reported usage (e.g. OpenAI streaming without include_usage) we do not invent zeros."""
    e = new_event("openai", "/v1/chat/completions")
    assert e.total_tokens is None


def test_output_input_ratio():
    e = new_event("anthropic", "/v1/messages", input_tokens=100, output_tokens=350)
    assert e.output_input_ratio == 3.5


def test_output_input_ratio_is_none_without_input():
    e = new_event("anthropic", "/v1/messages", output_tokens=350)
    assert e.output_input_ratio is None


def test_dict_roundtrip():
    e = new_event(
        "anthropic",
        "/v1/messages",
        model="claude-opus-4-8",
        agent="estimation_agent",
        input_tokens=10,
        output_tokens=20,
        quality_detail={"json_valid": True},
    )
    back = CallEvent.from_dict(e.to_dict())
    assert back == e


def test_from_dict_ignores_unknown_keys():
    """Forward tolerance: an event from a future schema must not break reading."""
    e = new_event("openai", "/v1/chat/completions")
    data = e.to_dict() | {"field_from_the_future": 42}
    assert CallEvent.from_dict(data).id == e.id
