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

For a future Mac mini v0.7 deployment, prefer a private Tailscale/SSH path or a
separate authenticated FabOps gateway on the MacBook Pro. Do not bind the raw
LM Studio API to the public internet.

## Vertex AI fallback

Development configuration:

```bash
export FABOPS_NARRATION_MODE=vertex
export FABOPS_VERTEX_PROJECT=flai-oosuhada-20260506
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

The current `fabops-preview.oosu.dev` v0.6.0 preview remains read-only during M8
and does not expose live paid generation.

If v0.7 is later made public, prefer pre-generated/cached grounded briefs for
anonymous users, with server-side call budgets/rate limits. A public browser
must never be able to select arbitrary providers, models, prompts or billing
projects.

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
