# Technical Spec — llm-observability

> ADD stage: **Specify**. Artifact proposed by the agent, approved by the human.
> Date: 11-07-2026 · Status: **APPROVED** (11-07-2026) · Depends on: [PRD](../define/prd.md) (approved)
>
> Settled decisions: stack **FastAPI + httpx** · tests against a **mock provider** (fake SSE).

Exact contracts: proxy, streaming, data schema, pricing, reporter and CLI.
No implementation code here — this is the precise "what", not the "how".

---

## 1. Components and single responsibility

```
llmobs/
  gateway/     ← receives HTTP, forwards to the provider, orchestrates measurement
    adapters/  ← anthropic.py, openai.py  (per-provider usage parsing)
  recording/   ← CallEvent, Recorder (SQLite + JSONL)
  pricing/     ← PricingTable, cost calculation
  evaluating/  ← Evaluator (interface) + JsonSchemaEvaluator (reference)
  reporting/   ← queries + rendering of report.md and metrics.json
  cli.py       ← commands: serve, report, pricing
  config.py    ← config loading (env + files)
```

Dependency rule (one direction only):

```
gateway → recording → pricing
gateway → evaluating
reporting → recording (read-only)
```

`recording` does not know about `gateway`. `pricing` knows about nobody. No cycles.

---

## 2. Gateway contract (HTTP)

### 2.1 Routes

| Method | Path | Detected provider | Forwards to |
|--------|------|-------------------|-------------|
| POST | `/v1/messages` | anthropic | `{ANTHROPIC_BASE_URL}/v1/messages` |
| POST | `/v1/chat/completions` | openai | `{OPENAI_BASE_URL}/v1/chat/completions` |
| GET | `/healthz` | — | returns `{"status":"ok"}` |

`ANTHROPIC_BASE_URL` (default `https://api.anthropic.com`) and `OPENAI_BASE_URL`
(default `https://api.openai.com`) are configurable → this is what lets you point at
Azure, OpenRouter, Ollama (`http://localhost:11434/v1`), etc.

### 2.2 Headers

| Header | Treatment |
|--------|-----------|
| `x-api-key`, `authorization`, `anthropic-version`, `content-type`, `accept` | **Forwarded** to the provider unmodified and unstored |
| `x-obs-project`, `x-obs-agent`, `x-obs-run-id`, `x-obs-tag` | **Consumed** by the proxy, **never** forwarded |
| everything else | Forwarded by default (minimal blocklist) |

### 2.3 Forwarding semantics
- Request body: passthrough, unaltered.
- `model` and `stream` are **read** from the JSON body for the event (never modified).
- Non-streaming response: read the status, parse `usage`, return the body intact.
- Streaming response: see §3.
- Provider errors (4xx/5xx): status and body propagated intact; event recorded with `outcome="error"`.
- Network failure reaching the provider: return `502` to the client with a JSON error body from the proxy; event recorded with `outcome="timeout"|"error"`.

### 2.4 Robustness invariant (NFR-4)
All measurement/persistence logic runs inside a block that, if it throws, is **logged
separately** while the provider's response is still returned. Observability never alters
the result the client sees.

---

## 3. Streaming (the sharp edge)

Both providers use **SSE** (`text/event-stream`).

### 3.1 General strategy
- The proxy does **incremental passthrough**: it forwards each chunk to the client as it arrives (never buffering the full response) → satisfies NFR-3 and adds no perceived latency.
- In parallel, an **accumulator** inspects the chunks to extract the final `usage`.
- The `CallEvent` is emitted when the stream closes (terminal event), with the tokens already accumulated.

### 3.2 Where `usage` comes from when streaming

**Anthropic** (`/v1/messages`, `stream:true`):
- `message_start` → carries `usage.input_tokens` (and an initial `output_tokens`).
- `message_delta` → carries the running `usage.output_tokens`.
- `message_stop` → end. Take the last `output_tokens` seen.

**OpenAI** (`/v1/chat/completions`, `stream:true`):
- Requires the client to pass `stream_options:{"include_usage":true}` to receive `usage`.
- If the client does **not** ask for it, no `usage` arrives in the stream → fallback:
  - `cost_status = "unknown_tokens"`, estimated tokens = `null`.
  - The reporter may optionally estimate output tokens by counting locally (tiktoken) as an approximation flagged `estimated=true`. (Optional in v1, configurable.)

### 3.3 `ttfb_ms` vs `total_ms`
- `ttfb_ms`: first chunk received from the provider.
- `total_ms`: terminal event of the stream.

---

## 4. Provider adapters (contract)

Each adapter implements:

```python
class ProviderAdapter(Protocol):
    name: str                       # "anthropic" | "openai"
    def target_url(self, base: str) -> str: ...
    def read_request_meta(self, body: dict) -> RequestMeta      # model, stream
    def parse_usage_nonstream(self, resp_json: dict) -> Usage   # input/output tokens
    def parse_usage_stream(self, sse_events: Iterable[bytes]) -> Usage
```

`Usage = {input_tokens:int|None, output_tokens:int|None}`.
Adding a new provider = one file implementing this protocol. Nothing else changes.

---

## 5. Persistence

### 5.1 SQLite — `call_events` table
One column per `CallEvent` field (PRD §5). Indexes on `ts_start`, `project`, `agent`,
`model`. `quality_detail` and other nested values are stored as JSON (TEXT).

```sql
CREATE TABLE call_events (
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
CREATE INDEX idx_ts ON call_events(ts_start);
CREATE INDEX idx_project_agent ON call_events(project, agent);
CREATE INDEX idx_model ON call_events(model);
```

### 5.2 JSONL
Append-only at `data/events.jsonl`, one serialized `CallEvent` per line. This is the
portable source of truth; SQLite is a query index that can always be rebuilt from it.

Data location: `LLMOBS_DATA_DIR` (default `./data`).

---

## 6. Pricing

`pricing.yaml`:

```yaml
as_of: 2026-07-01
currency: USD
models:
  claude-opus-4-8:     { input: 5.00,  output: 25.00 }   # USD per 1M tokens
  claude-sonnet-5:     { input: 3.00,  output: 15.00 }
  claude-haiku-4-5:    { input: 0.80,  output: 4.00 }
  gpt-4o:              { input: 2.50,  output: 10.00 }
# input/output = price per 1,000,000 tokens
```

> Illustrative values — to be validated against official pricing during implementation.
> `cost = in_tok/1e6*input + out_tok/1e6*output`.
Missing model → `cost=null`, `cost_status="unknown_model"`, warning logged.

---

## 7. Quality evaluator (pluggable, optional)

```python
class Evaluator(Protocol):
    def evaluate(self, request_body: dict, response_json: dict) -> QualityResult
# QualityResult = {score: float [0..1], detail: dict}
```

Reference `JsonSchemaEvaluator(schema)`: validates that the output is JSON conforming to a
schema and computes completeness = required fields present / total. Disabled unless
configured. Does not run on streaming in v1 (it needs the complete response).

---

## 8. Reporter — API and output

### 8.1 CLI
```
llmobs report [--since DD-MM-YYYY] [--until DD-MM-YYYY]
              [--project P] [--agent A] [--run-id R]
              [--format md|json|both]   (default both)
              [--out DIR]               (default ./data/reports)
```

### 8.2 `metrics.json` (structure)
```jsonc
{
  "generated_at": "2026-07-11T10:40:00Z",
  "window": { "since": "01-07-2026", "until": "11-07-2026" },
  "totals": { "calls": 128, "cost": 3.42, "input_tokens": 210000,
              "output_tokens": 88000, "error_rate": 0.02 },
  "by_model":   [ { "model": "...", "calls": 0, "cost": 0.0, "avg_cost": 0.0 } ],
  "by_project": [ ... ],
  "by_agent":   [ { "agent": "estimation_agent", "cost": 1.9,
                    "output_input_ratio": 3.4, "flag_high_ratio": true,
                    "avg_quality": 1.0 } ],
  "latency":    { "p50_ms": 800, "p95_ms": 2100,
                  "corr_latency_output_tokens": 0.93,
                  "corr_latency_input_tokens": 0.11 },
  "ab_variants":[ { "tag": "prompt=A", "avg_cost": 0.02, "avg_quality": 1.0,
                    "cost_per_quality": 0.02 },
                  { "tag": "prompt=B", "avg_cost": 0.012, "avg_quality": 1.0,
                    "cost_per_quality": 0.012, "winner": true } ]
}
```

### 8.3 `report.md`
A readable rendering of the above: cost per agent/model, flags for ratios above 3x, the
latency↔output correlation block, and (when A/B tags are present) the winning variant by
cost-per-quality.

---

## 9. Full CLI

```
llmobs serve   [--port 8900] [--data-dir ./data] [--capture-bodies]
llmobs report  [...]                 (see §8.1)
llmobs pricing [--check]             validate pricing.yaml and list known models
```

Config precedence: CLI flags > environment variables > files > defaults.
Variables: `LLMOBS_PORT`, `LLMOBS_DATA_DIR`, `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`,
`LLMOBS_CAPTURE_BODIES`.

---

## 10. How a client project connects (example)

```bash
# Any language: just change the base_url and add optional labels
export ANTHROPIC_BASE_URL=http://localhost:8900       # the Anthropic SDK honors this env var
# or in the OpenAI client: base_url="http://localhost:8900/v1"
```
Per-agent labels (headers): `x-obs-project: p8-agents`, `x-obs-agent: estimation_agent`.

---

## 11. Acceptance criteria for this spec

- [x] One non-streaming and one streaming request are fully specified for both providers.
- [x] The robustness invariant (§2.4) is explicit.
- [x] The fallback for missing `usage` in OpenAI streaming (§3.2) is defined.
- [x] The SQLite schema mirrors the `CallEvent` 1:1.
- [x] The reporter covers all six points of RF-6 plus A/B (RF-8).
