# FabOps grounded narration providers

## Purpose

FabOps v0.7 can use an LLM to generate manager/engineer **wording** from an
already accepted deterministic Decision Packet.

The LLM is not allowed to own or change:

- anomaly score,
- classification,
- RCA ranking,
- accepted recommendation ID,
- workflow authorization/state,
- equipment control.

Any provider, parse, schema or grounding failure falls back to deterministic
wording.

## Provider order

`FABOPS_NARRATION_MODE=auto` resolves providers in this order:

1. MacBook Pro LM Studio, when `FABOPS_LOCAL_LLM_BASE_URL` is configured;
2. Vertex AI Gemini, when `FABOPS_VERTEX_PROJECT` is configured;
3. deterministic template fallback.

The UI requests a brief only when a user opens `Decision & Approval`, and the
API caches the same case/audience packet for a bounded TTL to avoid repeated
generation.

For a public deployment, opening the page does **not** imply provider generation.
With `FABOPS_PUBLIC_NARRATION_CACHE_ONLY=true`, `GET /decision-brief` only reads
an existing cache entry and otherwise returns deterministic wording. A live LLM
call is available only through the bounded demo endpoint described below.

## MacBook Pro local model

The existing Biz-CollabCraft PR-review gateway remains independent. FabOps does
**not** call `/v1/review`, because that service has a fixed code-review policy.

FabOps may reuse the same LM Studio model instance through the OpenAI-compatible
LM Studio API. For development from the MacBook Air, use an SSH tunnel rather
than exposing LM Studio publicly:

```bash
bash scripts/local_llm_tunnel.sh

export FABOPS_NARRATION_MODE=local
export FABOPS_LOCAL_LLM_BASE_URL=http://127.0.0.1:12345/v1
export FABOPS_LOCAL_LLM_MODEL=local-review-qwen-next
export FABOPS_LOCAL_LLM_TIMEOUT_SECONDS=45
```

The observed Qwen model is large enough that cold load takes materially longer
than a normal API request. The PR-review environment already loads it under the
identifier `local-review-qwen-next`; FabOps can share that loaded instance
without creating a second model copy.

For a Mac mini v0.7 deployment, use a private Tailscale/SSH path and a separate
authenticated FabOps gateway on the MacBook Pro. The public repository contains
the generic gateway implementation in `services/narration/gateway.py`; real host
bindings and runtime credentials belong to a private operations repository. Do
not bind the raw LM Studio API to the public internet.

## Vertex AI fallback

Development configuration:

```bash
export FABOPS_NARRATION_MODE=vertex
export FABOPS_VERTEX_PROJECT=your-gcp-project-id
export FABOPS_VERTEX_LOCATION=global
export FABOPS_VERTEX_MODEL=gemini-2.5-flash-lite
```

Authentication modes:

- `FABOPS_VERTEX_AUTH_MODE=adc` — preferred for managed/server use;
- `FABOPS_VERTEX_AUTH_MODE=gcloud` — explicit local-development fallback using
  the currently logged-in `gcloud` user. Do not use this as the Mac mini
  production identity.

For production, use a least-privilege service identity/ADC rather than checking
in a service-account key.

## Public preview policy

The public preview separates ordinary reads from live generation:

- normal `GET`/`HEAD`: cache-only narration; a cache miss uses deterministic
  wording and performs zero provider calls;
- `POST /api/demo/narration`: the only public live-generation route;
- request body contains only `case_id`, `audience` and a fixed intent enum;
- no arbitrary prompt/provider/model/project selection is accepted;
- a server-issued signed demo session is required;
- session/IP limits and provider RPM/concurrency/daily token/request budgets are
  enforced before network I/O;
- local provider failure/circuit/budget exhaustion falls through to Vertex;
- Vertex failure/circuit/budget exhaustion falls through to deterministic text.

Allowed public intents are intentionally bounded to manager summary, engineer
checklist, option trade-off comparison and counter-evidence review.

The private operations repository owns the actual Mac mini/MacBook Pro addresses,
Cloudflare ingress configuration, Vertex project binding, rollout/rollback and
runtime secret locations. None of those runtime credentials are required to
review or test this public repository.

## Provider governance

Each provider is wrapped by a fail-fast governor. Configurable controls include:

- requests per minute;
- max concurrent generations;
- daily request budget;
- conservative daily estimated-token budget;
- max output tokens;
- circuit-breaker failure threshold and cooldown.

The governor never creates an unbounded queue. A blocked provider is skipped and
the request falls through to the next provider/fallback immediately.

## Smoke checks

Deterministic fallback:

```bash
FABOPS_NARRATION_MODE=deterministic \
  uv run pytest -q tests/test_decision_support.py
```

Runtime status (once the API is running):

```bash
curl -sS http://127.0.0.1:8000/api/narration/status
```

The status endpoint exposes provider names/cache state only; it does not expose
credentials.
