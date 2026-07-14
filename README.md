# llm-observability

> **Make the real cost of AI visible, so you can optimize it.**
> An LLM observability layer that plugs into any project without coupling to its
> business logic — or its language.

---

## The problem

LLM cost is invisible by default. It arrives **aggregated** in the provider's bill at
the end of the month, with no way to tell which feature, which agent, or which prompt
produced it.

Without that attribution you cannot optimize — you optimize blind. And the existing
tools are either the provider's own (which locks you in) or SaaS that requires shipping
your traffic to a third party.

## The design decision

Most implementations would instrument *inside* the code, wrapping every call. This
project makes a different bet:

> **Cost happens at the HTTP call to the LLM API. Measure it there — not in the
> business code.**

A wrapper lives inside one language. A **proxy** lives at the network boundary and
serves them all equally: you connect a project by changing one environment variable,
without touching a line of its code.

```
  App (any language)                              Observability layer
  base_url → localhost:8900  ──►  [ Gateway ] ──► real API (Anthropic / OpenAI)
                                       │  measures tokens, cost, latency, errors
                                       ▼
                              Recorder → JSONL + SQLite
                              Pricing  → cost per call
                              Reporter → metrics.json + report.md
```

Context labels travel as HTTP headers (`x-obs-agent`, `x-obs-project`), which yields
**cost per agent without coupling any code**: the observed project imports nothing from
this layer.

---

## Status

Under construction. The data core works; **the gateway does not exist yet.**

| Milestone | Status |
|---|---|
| M1 — Skeleton, CLI and configuration | ✅ done |
| M2 — Data core: `CallEvent` + Recorder | ✅ done |
| M3 — Pricing engine | ⬜ pending |
| M4 — Gateway (non-streaming) | ⬜ pending |
| M5 — Gateway (SSE streaming) | ⬜ pending |
| M6 — Reporter | ⬜ pending |
| M7 — Quality evaluator | ⬜ pending |

**20 tests passing.** What actually runs today: persisting events, querying them, and
rebuilding the database from scratch.

## Running it

```bash
pip install -r requirements.txt
export PYTHONPATH=src

python -m pytest -q          # 20 tests
python -m llmobs.cli --help
python -m llmobs.cli status  # recorded events
python -m llmobs.cli rebuild # regenerate SQLite from events.jsonl
```

`serve`, `report` and `pricing` exist in the CLI but tell you which milestone they land in.

---

## Three decisions worth a look

**1. The JSONL is the source of truth; SQLite is disposable.**
Every event is written to an append-only JSONL *and* to SQLite. SQLite is only a query
index: `llmobs rebuild` regenerates it whole from the JSONL. The data is never held
hostage by the database engine.
→ [`store.py`](src/llmobs/recording/store.py)

**2. Observability must never bring down the application.**
If persistence fails (disk full, database locked), `record()` returns `False`, counts it
and logs it — but **does not raise**. The client still gets its response. An observer
that breaks what it observes is worthless. There is a test that proves it.
→ [`recorder.py`](src/llmobs/recording/recorder.py)

**3. Privacy by default.**
No API keys and no prompt bodies are ever stored. Body capture is *opt-in*
(`--capture-bodies`) and strictly for local debugging. The data never leaves your machine.

---

## The process: Agent-Driven Development

This project was **designed before it was written**, following ADD — *"agents propose,
humans decide."* Each stage produced an artifact that was reviewed and approved before
moving on to the next:

| Stage | Artifact | What it settles |
|---|---|---|
| Discovery | [`brief.md`](docs/discovery/brief.md) | The problem, the scope, and why a proxy |
| Define | [`prd.md`](docs/define/prd.md) | Requirements and the `CallEvent` schema |
| Specify | [`spec.md`](docs/specify/spec.md) | HTTP contract, SSE streaming, SQLite schema |
| Plan | [`plan.md`](docs/plan/plan.md) | Module architecture and the 8 milestones |

The spec settles the trickiest part of the project up front: **how to count tokens in
streaming responses** without buffering the stream — including the trap that OpenAI does
not send `usage` over SSE unless the client asks for `stream_options.include_usage`.

## Stack

Python 3.11+ · FastAPI + httpx (gateway) · SQLite · Typer · pytest
