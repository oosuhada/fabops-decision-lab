# Public product repository vs private operations repository

FabOps intentionally separates portfolio source code from the real demo
deployment topology.

## Public repository

This repository remains the portfolio artifact and contains:

- deterministic case/RCA/Decision Packet logic;
- grounded narration schema and validation;
- local/Vertex provider adapters;
- provider rate/concurrency/budget/circuit governance;
- signed bounded-demo session policy;
- the generic authenticated local narration gateway;
- frontend decision UX;
- tests, ADRs and safe environment examples.

It must not contain live credentials, private keys, access tokens or runtime
secret values.

## Private operations repository

The real Mac mini/MacBook Pro deployment is maintained separately in a private
repository. That repository may contain operationally specific but non-secret
data such as private-network addresses, real ports, hostnames, GCP project
binding, deployment paths, Cloudflare ingress configuration and rollback
evidence.

Credentials remain outside Git even there: target hosts generate/store them in
mode-0600 runtime files or platform credential stores.

## Public demo contract

The public URL may be linked from this repository. The public browser never
receives the MacBook Pro gateway credential or Google credential. Ordinary page
loads are cache-only for narration. Live generation requires the server-owned
bounded demo path and cannot mutate workflow state or control equipment.
