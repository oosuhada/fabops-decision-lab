# FabOps v0.7 — Reference adaptation plan

## What changes from v0.6

v0.6 asks the user to inspect a case and infer what matters. v0.7 starts with
the decision itself:

> What needs an engineering decision now, why, what are the options, what
> evidence supports each option, and what remains uncertain?

## Borrowed product ideas, reworked for FabOps

| Reference pattern | FabOps adaptation |
|---|---|
| Biz-CollabCraft grounded manager/engineer report | `decision-brief-v1` generated only from a deterministic `decision-packet-v1` |
| Data Formulator analysis thread | decision question → evidence → option comparison → role-aware brief, while keeping the domain decision fixed |
| OpenGenerativeUI / Tremor block catalog | future role-aware layouts choose from approved FabOps blocks rather than arbitrary generated markup |
| Predictive-maintenance priority/impact | decision queue exposes physical excursion, sensor verification and data-quality verification as different priority semantics |
| Palantir/OpenFoundry object workflow | Case/Lot/Equipment/Chamber remain navigable objects, but the work surface is organized around exceptions and decisions |

## v0.7 first slice

- Decision Cockpit as default landing page.
- Deterministic queue ordering.
- Explicit decision questions.
- Bounded options with tradeoffs and approval requirements.
- Synthetic-only impact summary with a clear non-financial basis.
- Manager vs Engineer grounded narration.
- Local MacBook Pro LM Studio provider.
- Vertex AI Gemini provider.
- Deterministic fallback if either provider is unavailable or violates the
  grounding contract.

## LLM authority boundary

The LLM owns **wording**, not the decision.

It may:

- summarize impact already present in the packet,
- explain supporting and contradicting evidence,
- phrase tradeoffs for a manager or engineer,
- restate uncertainty.

It may not:

- change anomaly score,
- change classification,
- change RCA ranking,
- invent financial loss,
- change the accepted option ID,
- authorize a workflow transition,
- mutate a case,
- execute equipment control.
