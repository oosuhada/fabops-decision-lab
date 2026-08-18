# FabOps Decision Lab — Mac mini Deployment

## Scope

This runbook deploys release `0.6.0` to the user's Mac mini as a project-isolated OrbStack/Docker Compose stack. It reuses operational patterns from the existing Mac mini services but does not reuse their secrets, databases, service names, networks, ports, or Cloudflare hostname.

The deployed application remains a deterministic synthetic portfolio system. PostgreSQL is authoritative, Redpanda is transport, Neo4j is a rebuildable projection, the external LLM is not required, and there is no equipment-control route.

## Fixed isolation contract

- Compose project: `fabops-decision-lab-macmini`
- Docker network: `fabops-decision-lab-macmini_private`
- API: `127.0.0.1:8210` by default
- Web: `127.0.0.1:8220` by default
- PostgreSQL, Redpanda and Neo4j: private Compose network only; no host-published ports
- Persistent data root: server-only `FABOPS_DATA_ROOT`, normally under `~/Services/fabops-decision-lab-data`
- Release source root: normally `~/Services/fabops-decision-lab/current`
- Public ingress: not changed by this deployment. `ontology.oosu.dev` is explicitly out of scope.

Every service and one-shot job has explicit CPU and memory ceilings. The long-running stack is intentionally bounded so it cannot consume the entire 16 GiB Mac mini alongside unrelated services.

## Server-only environment

Copy `infra/macmini/.env.example` to `infra/macmini/.env` on the Mac mini, replace the two credential placeholders with project-specific generated values, set `FABOPS_DATA_ROOT` to an absolute FabOps-only server path, and set `FABOPS_DEPLOY_GIT_SHA` to the release-package Git SHA.

```bash
chmod 0600 infra/macmini/.env
```

Never commit or print that file. The operational scripts refuse to run if its mode is not exactly `0600`.

## Release transfer

Transfer only a reproducible Git archive of the FabOps repository. Do not rsync the personal workspace, `.venv`, `node_modules`, local `.env`, browser reports, databases, or sibling repositories.

Recommended pattern from the MacBook Air:

```bash
git archive --format=tar HEAD -o /tmp/fabops-release.tar
scp /tmp/fabops-release.tar <server-ssh-alias>:<server-release-root>/<git-sha>.tar
```

Extract the archive into a release-specific directory and point `current` at that directory. The release manifest remains the canonical application identity; the deployment Git SHA identifies the packaging/deployment commit.

## Deploy / status / logs

From the extracted release root on Mac mini:

```bash
sh infra/macmini/scripts/deploy.sh
sh infra/macmini/scripts/status.sh
sh infra/macmini/scripts/logs.sh
```

Deployment order is PostgreSQL / Redpanda / Neo4j → topic initialization → migration + deterministic initialization → API → Web. The init job loads the deterministic seed-42 demo only when authoritative PostgreSQL is empty and verifies 373 events, 7 cases, a complete detection checkpoint and zero projection lag.

The Web image is same-origin: nginx proxies `/api/*` over the private Compose network to API. This avoids exposing a browser-visible database/broker/graph port and avoids a cross-origin dependency between localhost ports.

## Backup and isolated restore test

Create a PostgreSQL custom-format dump:

```bash
sh infra/macmini/scripts/backup.sh
```

Restore the newest dump into a temporary database inside the FabOps PostgreSQL container, validate event/case/migration rows, and automatically drop the temporary database:

```bash
sh infra/macmini/scripts/restore-test.sh
```

The restore test never targets an unrelated database and never replaces the active `fabops` database.

## Rollback

For an ordinary stop without deleting project data:

```bash
sh infra/macmini/scripts/rollback.sh stop
```

For the first-deployment rollback drill:

```bash
sh infra/macmini/scripts/rollback.sh first-deploy
```

That command removes only the FabOps Compose services/network, moves only FabOps PostgreSQL/Redpanda/Neo4j active data into a timestamped FabOps rollback-quarantine directory, and recreates empty active directories. No unrelated container, volume, database or service is modified. Re-running `deploy.sh` restores the current release from deterministic source inputs.

## Real Mac mini verification

After deployment, execute the container-backed regression inside the Mac mini API container:

```bash
docker compose --project-name fabops-decision-lab-macmini --env-file infra/macmini/.env -f infra/macmini/docker-compose.yml exec -T -e FABOPS_CONTAINER_INTEGRATION=1 api uv run pytest -q tests/test_m6_container_integration.py
```

Then verify API restart survival and the browser contract. For the browser smoke, create an SSH local forward from the MacBook Air and run the remote Playwright configuration:

```bash
ssh -N -L <local-port>:127.0.0.1:<server-web-port> <server-ssh-alias>
cd systems/web
FABOPS_M7_BASE_URL=http://127.0.0.1:18220 npm exec playwright test e2e/workbench.spec.ts -- --config=playwright.m7.config.ts
```

The browser test is expected to mutate only the FabOps governed demo workflow. The first-deployment rollback drill can then reset active FabOps data before the final redeploy.

## Public ingress boundary

The original M7 deployment deliberately stopped at localhost/Tailscale-SSH and
recorded public ingress as `UNVERIFIED`. During the active M8 burn-in, a separate
`fabops-preview.oosu.dev` **read-only** ingress was later added without rebuilding
or restarting the FabOps application containers. It routes through a dedicated
localhost-only preview proxy that forwards `GET`/`HEAD` and rejects mutating
methods before they reach the 0.6.0 Web/API stack.

`ontology.oosu.dev` remains unchanged, and PostgreSQL, Redpanda and Neo4j remain
private. The preview is not the full interactive approval workflow because the
deployed application still trusts client-supplied portfolio role headers rather
than an external authenticated principal. See `docs/operations/PUBLIC_DEMO.md`
and `evidence/m7/public-preview-summary.json` for the current security boundary
and post-M8 hardening requirements.
