# Implementation Plan — llm-observability

> ADD stage: **Plan**. Artifact proposed by the agent, approved by the human.
> Date: 11-07-2026 · Status: **APPROVED** (14-07-2026) · Depends on: [spec](../specify/spec.md) (approved)

How it gets built, in what order, and how each piece is verified.

---

## 1. Stack and dependencies

| Area | Choice |
|------|--------|
| Language | Python 3.11+ |
| HTTP server | FastAPI + uvicorn |
| HTTP client (forwarding) | httpx (async, supports streaming) |
| Database | sqlite3 (stdlib) |
| Config/pricing | PyYAML |
| CLI | typer |
| Tests | pytest + httpx ASGITransport + a mock SSE server |
| Lint/format | ruff |

Minimum `requirements.txt`: `fastapi uvicorn httpx pyyaml typer pytest ruff`.

---

## 2. Final folder structure

```
llm-observability/
  pyproject.toml
  requirements.txt
  pricing.yaml
  README.md
  docs/                 # ADD artifacts
  src/llmobs/
    __init__.py
    config.py           # M1
    cli.py              # M1 → completed milestone by milestone
    recording/
      event.py          # M2  CallEvent (dataclass + (de)serialization)
      recorder.py       # M2  JSONL + SQLite
      store.py          # M2  SQLite schema + queries
    pricing/
      table.py          # M3  loads pricing.yaml, computes cost
    gateway/
      app.py            # M4  FastAPI app, routes, robustness invariant
      forward.py        # M4  httpx forwarding (non-stream)
      stream.py         # M5  SSE passthrough + usage accumulator
      adapters/
        base.py         # M4  ProviderAdapter protocol
        anthropic.py    # M4/M5
        openai.py       # M4/M5
    evaluating/
      base.py           # M7  Evaluator protocol
      jsonschema_eval.py# M7  reference implementation
    reporting/
      queries.py        # M6  aggregations from SQLite
      report.py         # M6  metrics.json + report.md
  tests/
    mock_provider.py    # fake server (non-stream + SSE) for both formats
    test_*.py
```

Rule: `src/` for code, `docs/` for ADD artifacts (workspace convention).

---

## 3. Implementation order (milestones)

Each milestone is **independently verifiable** and leaves the system green.

### M1 — Skeleton + config (base) ✅
- `pyproject.toml`, `requirements.txt`, the `llmobs` package, `config.py`, `cli.py` with
  `serve`/`report`/`pricing` as stubs.
- **Verification**: `llmobs --help` works; `pytest` runs.

### M2 — Data core (recording) — *no network, no provider* ✅
- `CallEvent` + `Recorder` (JSONL+SQLite) + `store` (schema §5).
- **Verification**: a test that creates a `CallEvent`, persists it, reads it back from
  SQLite and rebuilds it from the JSONL. **This is the heart; it is tested before any
  networking exists.**

### M3 — Pricing
- `PricingTable` from `pricing.yaml`, cost calculation, the `unknown_model` case.
- **Verification**: tests for the calculation and for a missing model.

### M4 — Gateway, non-streaming (Anthropic + OpenAI)
- `app.py` with routes, httpx forwarding, adapters parsing non-stream `usage`,
  `x-obs-*` labels, the robustness invariant (§2.4), and event emission.
- **Verification**: with `mock_provider`, a POST to `/v1/messages` and to
  `/v1/chat/completions` forwards, measures and persists. A test for a provider failure →
  `error` event with the response propagated. A test for "persistence fails → the client
  still gets its response".

### M5 — Gateway, streaming (SSE)
- `stream.py`: incremental passthrough + accumulator; adapters' `parse_usage_stream`;
  the OpenAI fallback when `include_usage` is absent.
- **Verification**: `mock_provider` emits SSE; a test asserts the client receives the
  stream intact and the final event carries the correct tokens. A test for the OpenAI fallback.

### M6 — Reporter
- `queries.py` + `report.py`: `metrics.json` + `report.md` (cost per agent/model,
  output/input ratio, latency↔output correlation, A/B by tag).
- **Verification**: seed the database with synthetic events and assert every metric
  (including `flag_high_ratio` and the correlation).

### M7 — Quality evaluator (optional, closes v1)
- `Evaluator` protocol + `JsonSchemaEvaluator`. Optional integration for non-streaming.
- **Verification**: a test for valid output (high score) vs invalid (low score).

### M8 — End-to-end integration + usage docs
- E2E test: mock provider + proxy + a real report generated.
- `README` usage: how to connect a project (including the P8 agents in TypeScript) to the proxy.
- **Verification**: success criterion #1 from the brief runs end to end.

---

## 4. Testing strategy (spending zero real tokens)

- `tests/mock_provider.py`: a FastAPI app that mimics Anthropic and OpenAI, with
  deterministic non-streaming and streaming (SSE) responses, including `usage`.
- Gateway tests point `ANTHROPIC_BASE_URL`/`OPENAI_BASE_URL` at the mock.
- No real keys, no external network, reproducible in CI.
- Plus an optional manual smoke test against the real API (documented, not in CI).

---

## 5. Use of ADD / subagents

- Each milestone can be delegated to a subagent with a closed objective and its
  verification criterion. "Agents propose, humans decide": the diff is reviewed before moving on.
- Conventions: dates `dd-mm-yyyy`, code in `src/`, artifacts in `docs/`.

---

## 6. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Streaming breaks the token count or the latency | M5 isolated, with deterministic SSE tests before touching real APIs |
| Stale prices | `pricing.yaml` carries `as_of`; `llmobs pricing --check`; validated against official pricing at implementation time |
| Proxy overhead | async httpx + passthrough without buffering; measured E2E (NFR-1 < 15ms p95) |
| Format divergence between providers | One internal schema (`Usage`) + adapters; the rest of the system stays agnostic |

---

## 7. Definition of done for v1

- [ ] `llmobs serve` starts the proxy; an Anthropic client and an OpenAI client both use it with no code changes.
- [ ] Streaming and non-streaming measured correctly for both providers.
- [ ] `llmobs report` produces `metrics.json` + `report.md` with cost per agent, output/input ratio and the latency correlation.
- [ ] Robustness: an observability failure does not affect the client (proven by a test).
- [ ] Everything verifiable with `pytest`, spending no real tokens.
