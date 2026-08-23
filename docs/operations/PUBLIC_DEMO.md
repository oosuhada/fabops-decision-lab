# FabOps Decision Lab public demo boundary

## Current preview access

`https://fabops-preview.oosu.dev` currently exposes the **v0.7 decision-cockpit
candidate UI** as a public read-only portfolio preview. This is not a promoted
`0.7.0` release: the accepted authoritative base remains release `0.6.0` while
M8 continues. The candidate UI therefore labels itself `0.7 CANDIDATE` and
`BASE 0.6.0` rather than presenting an unverified release as complete.

Cloudflare Tunnel routes the hostname to a dedicated localhost-only nginx
preview proxy on the Mac mini. The proxy forwards only `GET` and `HEAD` to an
isolated candidate Web origin at `127.0.0.1:8250`; other HTTP methods are
rejected with `405` before they can reach the candidate application.

The candidate composition is separate from the active M8 application:

- candidate API: `127.0.0.1:8240`, local deterministic runtime,
- candidate Web: `127.0.0.1:8250`,
- candidate Compose project: `fabops-decision-lab-preview-v07`,
- current M8 API/Web remain on `8210`/`8220`,
- the current M8 PostgreSQL, Redpanda and Neo4j containers are not shared with
  the candidate runtime.

The active M8 application images, API/Web containers, database schema and demo
database are not rebuilt, redeployed, restarted or reset by candidate-preview
updates. PostgreSQL, Redpanda and Neo4j remain private to the original FabOps
Compose network. Public narration is deterministic fallback in this candidate
so anonymous GET traffic cannot consume local-LLM capacity or Vertex budget.

The current UI still renders its workflow controls. In the public read-only
preview those controls are intentionally non-functional because their POST
requests are rejected at ingress. This preview must not be described as the full
interactive approval workflow.

## `X-FabOps-Role` is not production authentication

The current portfolio frontend sends client-selected headers such as
`X-FabOps-Role: process_engineer` and `X-FabOps-Role: yield_lead`, together with
an `X-FabOps-Actor` label. The API consumes those strings as workflow-policy
inputs. There is no external user login, cryptographic identity assertion or
server-side mapping from an authenticated principal to those roles.

Therefore these headers are **not authentication** and must never be presented
as production authorization. A caller able to reach the mutable API directly
could otherwise assert an allowed portfolio role. The read-only ingress exists
specifically so unrestricted Internet traffic cannot reach that mutation model.

## Mutation endpoints in release 0.6.0

The deployed API contains these state-changing routes:

- `POST /api/cases/{case_id}/request-evidence`
- `POST /api/cases/{case_id}/actions/propose`
- `POST /api/cases/{case_id}/actions/approve`
- `POST /api/cases/{case_id}/actions/reject`
- `POST /api/cases/{case_id}/close`

They mutate only the synthetic portfolio workflow/case state and append audit
records. They cannot execute fab equipment, change a recipe, hold a physical lot
or issue MES/tool commands. The workflow service explicitly rejects equipment
control action types.

## What must change before an open anonymous interactive demo

An open interactive demo must not trust browser-supplied role headers. At least
one server-enforced demo policy boundary is required, together with isolation of
demo mutations from the burn-in/portfolio reference state. Suitable requirements
include:

1. a dedicated `public-demo` runtime mode with server-owned anonymous-demo
   identity and a fixed, least-privilege transition policy;
2. a resettable, isolated synthetic demo database or per-session synthetic state
   that is not the M8 authoritative PostgreSQL dataset;
3. server-side rejection/ignoring of caller-provided privileged role assertions;
4. bounded session lifetime, request/rate limits and deterministic reset behavior;
5. explicit audit labeling for anonymous-demo actions and protection against
   cross-session state leakage;
6. regression proving forbidden equipment-control actions remain impossible;
7. UI treatment that clearly distinguishes public demo state from a real
   authenticated production workflow.

## Recommended post-M8 architecture

After the 24-hour M8 soak and recovery gate are complete, build a separate public
demo composition instead of changing the currently measured release in place.
Keep the production-shaped read path and release evidence, but inject a
server-enforced anonymous demo policy and an isolated resettable synthetic state
store. The browser should receive a server-issued demo session identity; the
server, not the browser, should decide the effective workflow role and allowed
transitions. Public traffic should continue through a method/rate-limited edge,
with datastore/broker/graph ports private.

Real authentication can be added if a future scope requires named-user approval,
but it should be treated as a separate security feature rather than retroactively
calling `X-FabOps-Role` authentication.

## Data and actuation claim boundary

All process/events/cases shown by the portfolio are synthetic, while anomaly
classification, RCA, recommendations and evaluation results are inferred or
computed from those synthetic fixtures. No Samsung/internal-fab data is used.
There is no real equipment-control capability in the application or this preview.
