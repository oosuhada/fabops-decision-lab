# ADR-005 — Decision Cockpit and grounded narration

## Status

Proposed for the v0.7 candidate branch. It does not change the deployed v0.6.0
release while the M8 soak is in progress.

## Context

FabOps v0.6.0 proves deterministic ingestion, detection, RCA, governance,
replay, container integration and deployment. Its UI, however, still reads like
an engineering evidence dashboard: users must infer the actual decision from
metrics, rankings and workflow controls.

The local reference set and Biz-CollabCraft implementation show a stronger
decision-product pattern:

1. prioritize the object or exception that needs attention,
2. state the human decision as a question,
3. show operational impact and uncertainty before model detail,
4. compare bounded options and tradeoffs,
5. generate role-aware wording from a governed evidence package,
6. fail closed to deterministic output when an LLM/provider/schema/grounding
   check fails.

## Decision

Introduce a deterministic `Decision Packet` and make `Decision Cockpit` the
default v0.7 work surface.

The deterministic domain layer owns:

- queue priority,
- decision question,
- accepted recommendation ID,
- option set and human-approval requirements,
- impact fields derived from synthetic evidence,
- RCA evidence and uncertainty,
- provenance and equipment-control prohibition.

An LLM may only produce role-aware wording from this packet. The narration
layer cannot change classification, RCA ranking, accepted recommendation, case
state, authorization or equipment behavior.

Provider order for private/internal use is configurable:

1. MacBook Pro LM Studio over a private SSH/Tailscale path,
2. Vertex AI Gemini for fallback or explicit cloud mode,
3. deterministic template fallback.

Every LLM output is schema-constrained, grounding-checked and rejected if it
references unknown evidence or makes forbidden operational claims.

## Reference patterns adapted

- **Biz-CollabCraft report agent:** role-aware grounded report, schema
  validation, evidence references and deterministic fail-closed fallback.
- **Microsoft Data Formulator:** an analysis/decision thread where generated
  specifications remain constrained instead of allowing arbitrary UI/HTML.
- **OpenGenerativeUI / Tremor:** approved block catalogs rather than arbitrary
  model-generated components.
- **Predictive-maintenance references:** priority as a combination of risk,
  criticality and impact, followed by a human decision.
- **OpenFoundry / Palantir-style operating model:** object → relationship →
  exception → decision → governed action → outcome, not metrics in isolation.

The adaptation is architectural; FabOps does not import their application code
or claim their data/model performance.

## Consequences

### Positive

- the first screen answers “what do I need to decide now?”;
- manager and engineer wording can differ without changing the underlying
  decision object;
- local inference can be used at zero cloud-token cost when available;
- Vertex AI can be used selectively without becoming a release dependency;
- public read-only demos can later serve cached/pre-generated briefs instead of
  exposing an anonymous paid-generation endpoint.

### Negative / constraints

- a 35+ GiB local model has meaningful cold-start and inference latency;
- LLM wording is non-deterministic and therefore never becomes authoritative
  evidence;
- Vertex AI requires a configured project, authentication and billing;
- provider telemetry and cost budgets need a separate v0.7 operational gate
  before deployment.
