from __future__ import annotations

import argparse
import json
from typing import Any

from systems.api.runtime import build_integration_runtime


def run_initialization() -> dict[str, Any]:
    runtime = build_integration_runtime(seed=42, profile="test")
    try:
        counts = runtime.event_repository.counts()
        projection = runtime.projection.status()
        integration = runtime.integration_status()
        checks = {
            "postgres_authoritative": integration["postgres_runtime_verified"] is True,
            "redpanda_available": integration["redpanda_runtime_verified"] is True,
            "neo4j_available": integration["neo4j_runtime_verified"] is True,
            "deterministic_demo_loaded": counts["events"] == 373 and counts["cases"] == 7,
            "detection_checkpoint_complete": runtime.event_repository.checkpoint("detection") == counts["events"],
            "projection_rebuilt": projection.source_checkpoint == counts["events"]
            and projection.projection_checkpoint == counts["events"]
            and projection.lag_events == 0,
            "equipment_control_disabled": runtime.health_status()["equipment_control_enabled"] is False,
        }
        return {
            "schema_version": "m7-init-v1",
            "seed": 42,
            "counts": counts,
            "projection": {
                "source_checkpoint": projection.source_checkpoint,
                "projection_checkpoint": projection.projection_checkpoint,
                "lag_events": projection.lag_events,
            },
            "integration": integration,
            "checks": checks,
            "passed": all(checks.values()),
        }
    finally:
        runtime.graph.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize and verify the Mac mini deterministic FabOps runtime.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = run_initialization()
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.check and not result["passed"]:
        failed = [name for name, value in result["checks"].items() if not value]
        raise SystemExit("M7 initialization failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
