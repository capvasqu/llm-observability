# PRD — llm-observability

> ADD stage: **Define**. Artifact proposed by the agent, approved by the human.
> Date: 11-07-2026 · Status: **APPROVED** (11-07-2026) · Depends on: [brief](../discovery/brief.md) (approved)
>
> Settled decisions: package/CLI `llmobs` · port `8900` · multi-provider routing by path.

---

## 1. Summary

The system is a **local HTTP gateway** that sits between a client project and an LLM
provider's API. It forwards the request without altering its semantics, measures the call,
persists a **normalized event**, and offers a cost/consumption report generator.

All the value revolves around a single entity: the **call event** (`CallEvent`).
Everything else (pricing, reporter, evaluator) consumes it.

---

## 2. Actors

| Actor | Description |
|-------|-------------|
| **Client project** | Any app that calls an LLM. It knows nothing about the system; it just points its `base_url` at the proxy. |
| **User/operator** | Starts the proxy, runs reports, decides on optimizations. |
| **LLM provider** | Anthropic or an OpenAI-compatible API. Receives the forwarded traffic. |

---

## 3. Functional requirements

### RF-1 — Transparent proxy
- RF-1.1 Exposes endpoints mirroring the provider's routes:
  - Anthropic: `POST /v1/messages`
  - OpenAI-compatible: `POST /v1/chat/completions`
- RF-1.2 Forwards **authentication headers** (`x-api-key`, `authorization`, `anthropic-version`) without reading or storing them.
- RF-1.3 The body and the response returned to the client are **identical** to the provider's (byte-for-byte when non-streaming; the stream intact when streaming). The client must not notice any functional difference.
- RF-1.4 If the provider returns an error, the proxy propagates the status and body as-is, and **still records** the event (with `outcome=error`).

### RF-2 — Measurement
For every call the system captures:
- RF-2.1 `model`, `provider`.
- RF-2.2 `input_tokens`, `output_tokens` (from the provider's response; when streaming, from the final usage event).
- RF-2.3 `latency_ms` (from receipt to first byte and to last byte: `ttfb_ms`, `total_ms`).
- RF-2.4 `outcome` ∈ {`ok`, `error`, `timeout`}, `http_status`, `error_type`.
- RF-2.5 `retries` if the proxy retries (optional config; 0 by default, no retries).

### RF-3 — Labeling without coupling
- RF-3.1 The client may send optional context headers:
  - `x-obs-project`, `x-obs-agent`, `x-obs-run-id`, `x-obs-tag` (free-form).
- RF-3.2 These headers are **not** forwarded to the provider (they are consumed by the proxy).
- RF-3.3 When absent, the fields are `null`; they never block a call.

### RF-4 — Pricing
- RF-4.1 A `model → {input_price_per_mtok, output_price_per_mtok, currency}` table in an editable file (`pricing.yaml`).
- RF-4.2 `cost = input_tokens/1e6 * in_price + output_tokens/1e6 * out_price`.
- RF-4.3 If the model is not in the table: `cost=null`, `cost_status="unknown_model"`, and a warning is logged (the event is never lost).
- RF-4.4 The table carries an `as_of` field (date) for price traceability.

### RF-5 — Persistence
- RF-5.1 Every event is written to **SQLite** (for queries/reports) **and** to an append-only **JSONL** (for audit/portability).
- RF-5.2 The schema is versioned (`schema_version`).
- RF-5.3 Prompt/response bodies are never persisted by default (privacy). Opt-in `--capture-bodies` for local debugging.

### RF-6 — Reports
- RF-6.1 A command that generates `report.md` + `metrics.json` from the database.
- RF-6.2 The report must answer, at minimum:
  - Total cost, and cost by `model`, by `project`, by `agent`.
  - Total tokens and the **output/input** ratio per agent (flagging those above 3x).
  - Latency p50/p95 and its correlation with output tokens.
  - Error rate by model/agent.
  - Number of calls and average cost per call.
- RF-6.3 Filters: date range, `project`, `agent`, `run_id`.

### RF-7 — Quality evaluation (pluggable module, non-blocking in v1)
- RF-7.1 An `Evaluator` interface that takes (request, response) and returns `quality_score ∈ [0,1]` plus detail.
- RF-7.2 Reference implementation: **JSON-schema** validation + **field completeness**.
- RF-7.3 It is optional and can be disabled; its absence must not affect cost measurement.

### RF-8 — Prompt refinement / A/B (minimal in v1, extensible)
- RF-8.1 Via the `x-obs-tag` label (e.g. `prompt=A` / `prompt=B`) the report can **group and compare** variants: average cost, average tokens and average quality score per variant.
- RF-8.2 The report flags the variant with the best **cost per unit of quality**.

---

## 4. Non-functional requirements

| NFR | Requirement |
|-----|-------------|
| NFR-1 | **Overhead** of the proxy below 15 ms p95 on top of the provider's latency (excluding network to the provider). |
| NFR-2 | **Local-first**: no network dependencies other than forwarding to the provider. |
| NFR-3 | **Streaming** supported without buffering the whole response: incremental passthrough while accumulating usage on the fly. |
| NFR-4 | **Robustness**: a failure in measurement or persistence must **never** bring down the client's call (the observability failure is recorded separately and the response is let through). |
| NFR-5 | **Portability**: the core installs as a Python package; starts with one command. |
| NFR-6 | **Privacy**: no keys and no bodies stored by default. |

---

## 5. Event schema (`CallEvent`) — the central contract

```jsonc
{
  "schema_version": "1.0",
  "id": "uuid",
  "ts_start": "2026-07-11T10:30:00.000Z",   // ISO-8601 UTC
  "ts_end":   "2026-07-11T10:30:01.240Z",

  // Origin / labels (from x-obs-* headers, may be null)
  "project":  "p8-agents",
  "agent":    "estimation_agent",
  "run_id":   "run_2026-07-11_001",
  "tag":      "prompt=A",

  // Provider / model
  "provider": "anthropic",                   // "anthropic" | "openai"
  "endpoint": "/v1/messages",
  "model":    "claude-opus-4-8",
  "streaming": true,

  // Consumption
  "input_tokens":  1520,
  "output_tokens": 640,
  "total_tokens":  2160,

  // Cost (computed by the pricing engine)
  "cost":        0.0672,
  "currency":    "USD",
  "cost_status": "ok",                       // "ok" | "unknown_model"
  "pricing_as_of": "2026-07-01",

  // Performance
  "ttfb_ms":  380,
  "total_ms": 1240,
  "retries":  0,

  // Result
  "outcome":     "ok",                       // "ok" | "error" | "timeout"
  "http_status": 200,
  "error_type":  null,

  // Quality (optional, when an Evaluator is active)
  "quality_score":  1.0,
  "quality_detail": { "json_valid": true, "fields_complete": 1.0 }
}
```

> This JSON is the contract between **all** modules. Any change to it is a
> `schema_version` change and is documented in Specify.

---

## 6. Out of scope (explicit)

- In-process wrapper/SDK (stage 2).
- Web dashboard (stage 2+).
- Native OpenTelemetry GenAI export (stage 2+; the schema above maps onto it cleanly).
- Load balancing / caching / rate limiting (this is not a production gateway, it is an
  observability one).

---

## Acceptance criteria for this PRD

- [x] The `CallEvent` schema covers the 5 requirements from the brief.
- [x] Streaming and robustness (NFR-3, NFR-4) are captured as first-class requirements.
- [x] The quality evaluator is pluggable and non-blocking, per the decision in the brief.
