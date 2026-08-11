from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from services.ingestion.adapters import InMemoryCaseRepository, InMemoryEventRepository
from services.rca.graph import InMemoryGraphProjection
from services.rca.projection import RcaProjectionWorker


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def recover(input_path: Path, output_path: Path) -> dict[str, Any]:
    source = json.loads(input_path.read_text(encoding="utf-8"))
    events = InMemoryEventRepository()
    events.restore(source["event_repository"])
    cases = InMemoryCaseRepository()
    cases.restore(source["case_repository"])
    graph = InMemoryGraphProjection()
    projection = RcaProjectionWorker(events, graph)
    projection_status = projection.rebuild()
    result = {
        "recovery_scope": "local deterministic snapshot restore plus projection rebuild",
        "event_count": len(events.all_events()),
        "case_count": len(cases.list_cases()),
        "case_hash": canonical_hash(cases.list_cases()),
        "audit_hash": canonical_hash(cases.audit_log()),
        "case_states": {item["case_id"]: item["state"] for item in cases.list_cases()},
        "projection": asdict(projection_status),
        "node_count": len(graph.nodes()),
        "edge_count": len(graph.edges()),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover a local FabOps snapshot in a fresh Python process.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    recover(args.input, args.output)


if __name__ == "__main__":
    main()
