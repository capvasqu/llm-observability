# Discovery Brief — llm-observability

> ADD stage: **Discovery**. Artifact proposed by the agent, approved by the human.
> Date: 11-07-2026 · Status: **APPROVED** (11-07-2026)

---

## 1. Problem

When building with AI (agents, RAG, LLM pipelines) there is no systematic way to know
**how much each call costs, which agent burns the most tokens, or whether a prompt is
asking for more text than it needs**. Without that measurement, optimization is blind.

Existing tools are either the provider's own — which locks you in — or SaaS products
that require sending your traffic to a third party. This project wants something
**local, owned, and decoupled**, that plugs into *any* project without rewriting it.

## 2. Goal

A **standalone LLM observability layer** that measures cost, token consumption, latency,
errors and (optionally) output quality — and connects to any project **without coupling
to its business logic or its language**.

The ultimate purpose is not measurement for its own sake, but **enabling optimization**:
cutting cost, cutting latency, and refining prompts with data instead of intuition.

## 3. User requirements (explicit)

| # | Requirement | How this proposal satisfies it |
|---|-------------|--------------------------------|
| R1 | The layer must be **decoupled** from all business logic | The core is a standalone package; observed projects import no logic from it |
| R2 | It must connect to **any project** | Proxy mode: change `base_url`, zero code. Works with any language |
| R3 | Use **Agent-Driven Development (ADD)** | Staged artifacts under `docs/`, subagents in `.claude/agents/`, "agents propose, humans decide" |
| R4 | Enable **monitoring and optimization** of AI usage | Cost-per-agent reports, output/input ratio, latency↔output correlation |
| R5 | Enable **prompt refinement** | A/B mode: compare prompt variants by cost and quality |

## 4. Scope

### In (v1)
- **Gateway/proxy** compatible with the Anthropic Messages API and the OpenAI Chat Completions API.
- **Recorder**: persists every call (model, in/out tokens, cost, latency, error, retries) to SQLite + JSONL.
- **Pricing engine**: an editable `model → price` table that computes per-call cost.
- **Reporter**: produces `metrics.json` + a readable `report.md`.
- **Label** support (`project`, `agent`, `run_id`) via HTTP headers, for cost-per-agent without coupling code.

### Out (v1, possibly v2)
- In-process wrapper/SDK for richer labels (second stage).
- Quality evaluator (JSON-schema / completeness) — kept as a pluggable, non-blocking module.
- Local web dashboard, automated prompt A/B, OpenTelemetry GenAI export.

## 5. Constraints and decisions taken

- **Core language**: Python (FastAPI for the proxy).
- **v1 providers**: Anthropic (Claude) + OpenAI-compatible (OpenAI, Azure, OpenRouter, Ollama, LM Studio).
- **v1 integration**: proxy first (maximum decoupling); label wrapper later.
- **Local-first**: no traffic sent to third parties; data stays on the user's disk.
- **Dates**: `dd-mm-yyyy` format (workspace convention).

## 6. Key design principle (why a proxy)

The real cost happens at the **HTTP call to the LLM**. Intercepting there — rather than
inside the business code — is what makes the layer genuinely language-agnostic and
reusable. A wrapper lives inside one language; a proxy lives at the network boundary and
serves them all equally.

## 7. Success criteria

1. Point an existing project (e.g. the P8 agents written in TypeScript) at the proxy by
   changing one environment variable, and **it starts recording cost without touching its code**.
2. Produce a `report.md` that answers: *which agent/model costs the most? which one has an
   output/input ratio above 3x? does latency correlate with output?*
3. Compare two versions of a prompt and see which costs less per unit of quality.

## 8. Risks / things to validate

- **Streaming (SSE)**: the proxy must reassemble the token count for streaming responses
  without breaking the stream flowing to the client. This is the sharpest technical edge.
- **Changing prices**: the pricing table must be easy to update and version.
- **Anthropic vs OpenAI format differences**: two adapters, one shared internal schema.

---

## Next ADD stages (after this brief was approved)

1. **Define** → `docs/define/prd.md` (detailed functional requirements + data schema).
2. **Specify** → `docs/specify/spec.md` (proxy contract, event schema, reporting API).
3. **Plan** → `docs/plan/plan.md` (module architecture, implementation order).
4. **Tasks** → executable task list.
5. Implementation by subagents.
