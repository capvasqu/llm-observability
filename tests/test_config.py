"""M1 — configuration precedence: defaults < environment < overrides."""

from pathlib import Path

from llmobs.config import Config


def test_defaults(monkeypatch):
    for var in ("LLMOBS_PORT", "LLMOBS_DATA_DIR", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)

    c = Config.load()
    assert c.port == 8900
    assert c.data_dir == Path("./data")
    assert c.anthropic_base_url == "https://api.anthropic.com"
    assert c.capture_bodies is False  # privacy by default (RF-5.3)


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("LLMOBS_PORT", "9999")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1/")  # e.g. Ollama

    c = Config.load()
    assert c.port == 9999
    assert c.openai_base_url == "http://localhost:11434/v1"  # trailing slash stripped


def test_explicit_overrides_beat_the_environment(monkeypatch):
    monkeypatch.setenv("LLMOBS_PORT", "9999")

    c = Config.load(port=7000)
    assert c.port == 7000


def test_none_overrides_are_ignored(monkeypatch):
    """A CLI flag left unset arrives as None and must not wipe the environment value."""
    monkeypatch.setenv("LLMOBS_PORT", "9999")

    c = Config.load(port=None, data_dir=None)
    assert c.port == 9999


def test_derived_paths():
    c = Config.load(data_dir="/tmp/x")
    assert c.db_path == Path("/tmp/x/llmobs.db")
    assert c.jsonl_path == Path("/tmp/x/events.jsonl")
    assert c.reports_dir == Path("/tmp/x/reports")
