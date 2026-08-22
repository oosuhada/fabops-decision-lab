from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.observability.context import canonical_trace_id
from services.observability.telemetry import TelemetryRecorder
from services.rca.cqrs import RankRootCausesQuery
from services.reliability import CircuitBreaker, CircuitBreakerOpen
from systems.api.runtime import build_local_runtime

EVIDENCE_VERSION = "m6-telemetry-reliability-v1"


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _fixed_clock() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _exercise_breaker() -> dict[str, Any]:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=5.0, clock=lambda: now[0])
    transitions = [breaker.snapshot()["state"]]

    def fail() -> None:
        raise RuntimeError("deterministic dependency failure")

    for _ in range(2):
        try:
            breaker.call(fail)
        except RuntimeError:
            transitions.append(breaker.snapshot()["state"])
    rejected_while_open = False
    try:
        breaker.call(lambda: "should-not-run")
    except CircuitBreakerOpen:
        rejected_while_open = True
    now[0] = 5.0
    transitions.append(breaker.snapshot()["state"])
    recovered_value = breaker.call(lambda: "recovered")
    transitions.append(breaker.snapshot()["state"])
    return {
        "transitions": transitions,
        "rejected_while_open": rejected_while_open,
        "recovered_value": recovered_value,
        "final_state": breaker.snapshot()["state"],
    }


def generate(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    telemetry = TelemetryRecorder(clock=_fixed_clock)
    runtime = build_local_runtime(telemetry=telemetry)
    case = runtime.case_repository.list_cases()[0]
    case_id = str(case["case_id"])
    causal_trace_id = next(
        str(item.event["trace_id"])
        for item in runtime.event_repository.all_events()
        if item.event.get("lot_id") == case["lot_id"] and item.event.get("trace_id")
    )
    correlation_id = "m6-evidence-correlation"
    with telemetry.bind_causal_trace(causal_trace_id, correlation_id):
        runtime.queries.execute(RankRootCausesQuery(case_id))
        runtime.advisory.advise(case_id)
        runtime.workflow.propose_action(case_id, "evidence-worker", "process_engineer", "diagnostic_review", str(case["lot_id"]), "M6 replay proof")
        runtime.workflow.approve(case_id, "evidence-lead", "yield_lead", "M6 deterministic approval proof")
        runtime.workflow.close(case_id, "evidence-lead", "yield_lead", "M6 local recovery proof complete")

    related_records = [record for record in telemetry.records() if record["trace_id"] == canonical_trace_id(causal_trace_id)]
    serialized_records = json.dumps(related_records, sort_keys=True)
    telemetry_summary = {
        "schema_version": EVIDENCE_VERSION,
        "service_name": telemetry.service_name,
        "record_count": len(telemetry.records()),
        "selected_trace_record_count": len(related_records),
        "causal_trace_id": causal_trace_id,
        "otel_trace_id": canonical_trace_id(causal_trace_id),
        "correlation_id": correlation_id,
        "operations": sorted({str(record["operation"]) for record in related_records}),
        "required_operations_present": all(
            operation in {str(record["operation"]) for record in related_records}
            for operation in (
                "ingestion.ingest",
                "detection.consume",
                "case.materialized",
                "projection.project_event",
                "rca.query",
                "advisory.tool_call",
                "advisory.advise",
                "workflow.action_proposed",
                "workflow.action_approved",
                "workflow.case_closed",
            )
        ),
        "ground_truth_present": "ground_truth" in serialized_records,
        "approval_token_raw_present": "." in "".join(
            str(record.get("approval_token", "")) for record in related_records if record.get("approval_token") != "[REDACTED]"
        ),
        "exporter": "in-memory-json",
        "external_collector_required": False,
    }
    (output_dir / "telemetry-summary.json").write_text(json.dumps(telemetry_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "trace-sample.json").write_text(json.dumps(related_records[-16:], indent=2, sort_keys=True) + "\n", encoding="utf-8")

    event_snapshot = runtime.event_repository.snapshot()
    case_snapshot = runtime.case_repository.snapshot()
    before = {
        "events": len(runtime.event_repository.all_events()),
        "outbox": len(runtime.event_repository.outbox()),
        "cases": len(runtime.case_repository.list_cases()),
        "audit": len(runtime.case_repository.audit_log()),
    }
    duplicate_attempts = 0
    duplicate_results = 0
    for stored in runtime.event_repository.all_events():
        duplicate_attempts += 1
        duplicate_results += runtime.ingestion.ingest(stored.event) == "duplicate_noop"
    after = {
        "events": len(runtime.event_repository.all_events()),
        "outbox": len(runtime.event_repository.outbox()),
        "cases": len(runtime.case_repository.list_cases()),
        "audit": len(runtime.case_repository.audit_log()),
    }
    side_effect_delta = sum(max(0, after[key] - before[key]) for key in after)
    duplicate_side_effect_rate = side_effect_delta / duplicate_attempts if duplicate_attempts else 0.0

    with tempfile.TemporaryDirectory(prefix="fabops-m6-replay-") as temp_dir:
        temp = Path(temp_dir)
        input_path = temp / "snapshot.json"
        output_path = temp / "recovered.json"
        input_path.write_text(
            json.dumps({"event_repository": event_snapshot, "case_repository": case_snapshot}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [sys.executable, "-m", "evaluation.m6_replay_worker", "--input", str(input_path), "--output", str(output_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        recovered = json.loads(output_path.read_text(encoding="utf-8"))

    case_hash = canonical_hash(runtime.case_repository.list_cases())
    audit_hash = canonical_hash(runtime.case_repository.audit_log())
    replay_completeness = recovered["projection"]["projection_checkpoint"] / recovered["event_count"] if recovered["event_count"] else 1.0
    reliability_summary = {
        "schema_version": EVIDENCE_VERSION,
        "recovery_scope": recovered["recovery_scope"],
        "restart_harness": "fresh Python subprocess",
        "subprocess_exit_code": completed.returncode,
        "event_count": recovered["event_count"],
        "case_hash_before": case_hash,
        "case_hash_after": recovered["case_hash"],
        "case_hash_identical": case_hash == recovered["case_hash"],
        "audit_hash_before": audit_hash,
        "audit_hash_after": recovered["audit_hash"],
        "audit_hash_identical": audit_hash == recovered["audit_hash"],
        "closed_case_survived": recovered["case_states"].get(case_id) == "closed",
        "projection_rebuilt": recovered["projection"]["projection_checkpoint"] == recovered["event_count"],
        "replay_completeness": replay_completeness,
        "duplicate_attempts": duplicate_attempts,
        "duplicate_noop_results": duplicate_results,
        "duplicate_side_effect_delta": side_effect_delta,
        "duplicate_side_effect_rate": duplicate_side_effect_rate,
        "circuit_breaker": _exercise_breaker(),
        "production_postgres_recovery_claimed": False,
    }
    (output_dir / "reliability-summary.json").write_text(json.dumps(reliability_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"telemetry": telemetry_summary, "reliability": reliability_summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate M6 telemetry and local reliability evidence.")
    parser.add_argument("--output-dir", type=Path, default=Path("evidence/m6"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = generate(args.output_dir)
    if args.check:
        telemetry = result["telemetry"]
        reliability = result["reliability"]
        passed = (
            telemetry["required_operations_present"]
            and not telemetry["ground_truth_present"]
            and not telemetry["approval_token_raw_present"]
            and reliability["case_hash_identical"]
            and reliability["audit_hash_identical"]
            and reliability["closed_case_survived"]
            and reliability["replay_completeness"] == 1.0
            and reliability["duplicate_side_effect_rate"] == 0.0
        )
        if not passed:
            raise SystemExit("M6 telemetry/reliability evidence check failed")


if __name__ == "__main__":
    main()
