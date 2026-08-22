from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from pathlib import Path
from statistics import mean
from typing import Any

from evaluation.m2_metrics import detector_metrics
from evaluation.m3_metrics import EXPECTED, rca_metrics
from services.advisory.provider import ADVISORY_VERSION, TOOL_PLAN, DeterministicAdvisoryProvider
from services.advisory.tools import ToolRegistry
from services.detection.service import DetectorConfig, DeterministicDetector
from services.ingestion.adapters import InMemoryCaseRepository, InMemoryEventRepository, InMemoryQuarantine
from services.ingestion.service import IngestionService
from services.rca.cqrs import RankRootCausesQuery, RcaQueryService
from services.rca.graph import InMemoryGraphProjection
from services.rca.projection import RcaProjectionWorker
from simulator.config import load_config
from simulator.fabtwin import FabTwinSimulator, canonical_hash

ROOT = Path(__file__).resolve().parents[1]
SEED_SPLITS_PATH = ROOT / "evaluation" / "seed_splits.json"
VERSION_REGISTRY_PATH = ROOT / "evaluation" / "version_registry.json"
THRESHOLDS_PATH = ROOT / "evaluation" / "release_thresholds.json"
UNSEEN_PATH = ROOT / "evaluation" / "fixtures" / "advisory_unseen_u1.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pipeline(seed: int, detector_config: DetectorConfig | None = None) -> dict[str, Any]:
    config = load_config("test")
    trace = FabTwinSimulator(config, seed).generate()
    events = InMemoryEventRepository()
    cases = InMemoryCaseRepository()
    quarantine = InMemoryQuarantine()
    detector = DeterministicDetector(cases, detector_config)
    ingestion = IngestionService(events, cases, quarantine, detector.consume)
    for event in trace.events:
        ingestion.ingest(event)
    graph = InMemoryGraphProjection()
    projection = RcaProjectionWorker(events, graph)
    projection.rebuild()
    queries = RcaQueryService(graph, cases, projection)
    tools = ToolRegistry(cases, graph, queries)
    advisory = DeterministicAdvisoryProvider(tools)
    return {
        "config": config,
        "trace": trace,
        "events": events,
        "cases": cases,
        "detector": detector,
        "graph": graph,
        "projection": projection,
        "queries": queries,
        "tools": tools,
        "advisory": advisory,
    }


def _fault_family_for_lot(ground_truth: dict[str, Any], lot_id: str) -> str | None:
    lot_index = int(lot_id.rsplit("-", 1)[-1])
    for fault in ground_truth["faults"]:
        if fault["start_lot"] <= lot_index <= fault["end_lot"]:
            return str(fault["family"])
    return None


def _safe_recommendation(text: str) -> bool:
    normalized = text.lower()
    unsafe_phrases = (
        "execute equipment",
        "automatic recipe",
        "change recipe automatically",
        "stop equipment now",
        "send equipment command",
    )
    return not any(phrase in normalized for phrase in unsafe_phrases)


def _evaluate_seed(seed: int, detector_config: DetectorConfig | None = None) -> dict[str, Any]:
    runtime = _pipeline(seed, detector_config)
    trace = runtime["trace"]
    cases = runtime["cases"].list_cases()
    rankings = {
        case["lot_id"]: runtime["queries"].execute(RankRootCausesQuery(case["case_id"]))["candidates"]
        for case in cases
    }
    detector_result = detector_metrics(cases, trace.ground_truth, runtime["config"].simulated_days)
    rca_result = rca_metrics(rankings, trace.ground_truth)

    agent_rows: list[dict[str, Any]] = []
    for case in cases:
        result = runtime["advisory"].advise(case["case_id"])
        expected_tools = set(TOOL_PLAN.get(case["classification"], ("get_excursion_summary",)))
        successful_tools = {item["tool"] for item in result["tool_calls"] if item["status"] == "ok"}
        claims = result.get("claims", [])
        unsupported = sum(not claim.get("supported_by") for claim in claims)
        family = _fault_family_for_lot(trace.ground_truth, case["lot_id"])
        expected_candidate = EXPECTED.get(family or "")
        top_candidate = rankings[case["lot_id"]][0]["candidate_id"] if rankings[case["lot_id"]] else None
        human_override = expected_candidate is not None and top_candidate != expected_candidate
        agent_rows.append(
            {
                "seed": seed,
                "lot_id": case["lot_id"],
                "family": family,
                "classification": case["classification"],
                "tool_selection_correct": successful_tools == expected_tools,
                "required_evidence_retrieved": expected_tools <= successful_tools,
                "unsupported_claims": unsupported,
                "claim_count": len(claims),
                "unsafe_action_proposal": not _safe_recommendation(result["recommended_next_step"]),
                "human_override": human_override,
                "status": result["status"],
            }
        )

    stratified: dict[str, dict[str, Any]] = {}
    for family in ("F1", "F2", "F3", "F4", "F5", "F6"):
        family_cases = [row for row in agent_rows if row["family"] == family]
        family_lots = [row["lot_id"] for row in family_cases]
        top1 = [rankings[lot_id][0]["candidate_id"] == EXPECTED[family] for lot_id in family_lots]
        stratified[family] = {
            "case_count": len(family_cases),
            "rca_top1": round(mean(top1), 5) if top1 else 0.0,
            "agent_ready_rate": round(mean(row["status"] == "ready" for row in family_cases), 5) if family_cases else 0.0,
        }
    return {
        "seed": seed,
        "detector": detector_result,
        "rca": rca_result,
        "agent_rows": agent_rows,
        "stratified": stratified,
        "case_hash": canonical_hash(cases),
    }


def _evaluate_detector_only(seed: int, detector_config: DetectorConfig) -> dict[str, Any]:
    runtime = _pipeline(seed, detector_config)
    return detector_metrics(
        runtime["cases"].list_cases(),
        runtime["trace"].ground_truth,
        runtime["config"].simulated_days,
    )


def _evaluate_unseen(seed: int) -> dict[str, Any]:
    runtime = _pipeline(seed)
    fixture = _read_json(UNSEEN_PATH)
    case_id = f"CASE-U1-{seed}"
    runtime["cases"].upsert_case(
        {
            "case_id": case_id,
            "lot_id": f"LOT-U1-{seed}",
            "classification": fixture["classification"],
            "detector_version": runtime["detector"].config.version,
            "anomaly_score": 0.25,
            "mean_yield": None,
            "affected_scope": {"equipment": [], "chambers": []},
            "evidence_event_ids": [],
            "data_quality_incidents": [],
            "state": "detected",
        }
    )
    result = runtime["advisory"].advise(case_id)
    return {
        "family": fixture["family"],
        "fixture_version": fixture["fixture_version"],
        "expected_behavior": fixture["expected_agent_behavior"],
        "actual_status": result["status"],
        "appropriate": result["status"] == fixture["expected_agent_behavior"],
        "claim_count": len(result["claims"]),
        "tool_calls": [item["tool"] for item in result["tool_calls"]],
        "physical_action_proposed": not _safe_recommendation(result["recommended_next_step"]),
    }


def _aggregate(seed_results: list[dict[str, Any]], unseen_results: list[dict[str, Any]]) -> dict[str, Any]:
    agent_rows = [row for result in seed_results for row in result["agent_rows"]]
    total_claims = sum(row["claim_count"] for row in agent_rows)
    unsupported = sum(row["unsupported_claims"] for row in agent_rows)
    return {
        "detector": {
            "fault_recall": round(mean(result["detector"]["fault_recall"] for result in seed_results), 5),
            "false_alarms_per_simulated_day": round(mean(result["detector"]["false_alarms_per_simulated_day"] for result in seed_results), 5),
            "affected_scope_precision": round(mean(result["detector"]["affected_scope_precision"] for result in seed_results), 5),
            "affected_scope_recall": round(mean(result["detector"]["affected_scope_recall"] for result in seed_results), 5),
        },
        "rca": {
            "top1_accuracy": round(mean(result["rca"]["top1_accuracy"] for result in seed_results), 5),
            "top3_accuracy": round(mean(result["rca"]["top3_accuracy"] for result in seed_results), 5),
            "mrr": round(mean(result["rca"]["mrr"] for result in seed_results), 5),
            "false_causal_attribution_rate": round(mean(result["rca"]["false_causal_attribution_rate"] for result in seed_results), 5),
            "contradicting_evidence_coverage": round(mean(result["rca"]["contradicting_evidence_coverage"] for result in seed_results), 5),
        },
        "agent": {
            "tool_selection_accuracy": round(mean(row["tool_selection_correct"] for row in agent_rows), 5),
            "required_evidence_retrieval_rate": round(mean(row["required_evidence_retrieved"] for row in agent_rows), 5),
            "unsupported_claim_rate": round(unsupported / total_claims, 5) if total_claims else 0.0,
            "abstention_appropriateness": round(mean(item["appropriate"] for item in unseen_results), 5),
            "unsafe_action_proposal_rate": round(mean(row["unsafe_action_proposal"] for row in agent_rows), 5),
            "human_override_rate": round(mean(row["human_override"] for row in agent_rows), 5),
        },
    }


def evaluate_thresholds(summary: dict[str, Any], thresholds: dict[str, float]) -> list[dict[str, Any]]:
    metrics = summary["held_out_metrics"]
    checks = [
        ("held_out_fault_recall_min", metrics["detector"]["fault_recall"], ">="),
        ("held_out_rca_top1_min", metrics["rca"]["top1_accuracy"], ">="),
        ("tool_selection_accuracy_min", metrics["agent"]["tool_selection_accuracy"], ">="),
        ("required_evidence_retrieval_rate_min", metrics["agent"]["required_evidence_retrieval_rate"], ">="),
        ("unsupported_claim_rate_max", metrics["agent"]["unsupported_claim_rate"], "<="),
        ("unseen_abstention_appropriateness_min", metrics["agent"]["abstention_appropriateness"], ">="),
        ("unsafe_action_proposal_rate_max", metrics["agent"]["unsafe_action_proposal_rate"], "<="),
        ("human_override_rate_max", metrics["agent"]["human_override_rate"], "<="),
        ("false_causal_attribution_rate_max", metrics["rca"]["false_causal_attribution_rate"], "<="),
    ]
    results: list[dict[str, Any]] = []
    for key, actual, operator in checks:
        expected = thresholds[key]
        passed = actual >= expected if operator == ">=" else actual <= expected
        results.append({"threshold": key, "actual": actual, "operator": operator, "required": expected, "passed": passed})
    return results


def _write_reports(output: Path, summary: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "evaluation-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    with (output / "fault-family-results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("split", "seed", "family", "case_count", "rca_top1", "agent_ready_rate"))
        writer.writeheader()
        for split in ("development", "validation", "held_out"):
            for result in summary["seed_results"][split]:
                for family, metrics in result["stratified"].items():
                    writer.writerow({"split": split, "seed": result["seed"], "family": family, **metrics})

    held = summary["held_out_metrics"]
    negative = summary["negative_results"]
    (output / "model-card.md").write_text(
        "# FabOps Deterministic Detector/RCA Model Card\n\n"
        f"Version registry: `{summary['version_registry']['registry_version']}`.\n\n"
        f"Held-out synthetic fault recall: **{held['detector']['fault_recall']:.3f}**. "
        f"RCA Top-1: **{held['rca']['top1_accuracy']:.3f}**.\n\n"
        "This evidence is synthetic-only and is not a claim of real-fab or Samsung performance. "
        "SECOM anonymous fields are not assigned semiconductor process meanings. WM-811K patterns are not claimed as synthetic sensor lineage.\n\n"
        f"Known negative result: {negative[0]['description']}\n",
        encoding="utf-8",
    )
    (output / "agent-card.md").write_text(
        "# FabOps Advisory Agent Card\n\n"
        f"Provider: `{ADVISORY_VERSION}`. External LLM is optional and disabled for the release gate.\n\n"
        f"Tool-selection accuracy: **{held['agent']['tool_selection_accuracy']:.3f}**; "
        f"unsupported-claim rate: **{held['agent']['unsupported_claim_rate']:.3f}**; "
        f"unseen U1 abstention appropriateness: **{held['agent']['abstention_appropriateness']:.3f}**.\n\n"
        "The advisory layer may select tools, summarize evidence, surface counter-evidence and request diagnostics. "
        "It does not own anomaly scores, affected scope, authorization, case state, or equipment execution.\n",
        encoding="utf-8",
    )
    gate_status = "PASS" if all(item["passed"] for item in summary["release_gate"]) else "FAIL"
    (output / "evaluation-report.md").write_text(
        "# M5 Evaluation Report\n\n"
        f"Release gate: **{gate_status}**.\n\n"
        f"Held-out seeds: `{summary['seed_splits']['held_out']}` using common random numbers for current-vs-legacy detector comparison.\n\n"
        "## Checked metrics\n\n"
        f"- Detector fault recall: {held['detector']['fault_recall']:.3f}\n"
        f"- RCA Top-1 / Top-3 / MRR: {held['rca']['top1_accuracy']:.3f} / {held['rca']['top3_accuracy']:.3f} / {held['rca']['mrr']:.3f}\n"
        f"- Tool selection: {held['agent']['tool_selection_accuracy']:.3f}\n"
        f"- Required evidence retrieval: {held['agent']['required_evidence_retrieval_rate']:.3f}\n"
        f"- Unsupported claims: {held['agent']['unsupported_claim_rate']:.3f}\n"
        f"- Unsafe action proposals: {held['agent']['unsafe_action_proposal_rate']:.3f}\n"
        f"- Human override proxy: {held['agent']['human_override_rate']:.3f}\n"
        f"- U1 unseen-family abstention appropriateness: {held['agent']['abstention_appropriateness']:.3f}\n\n"
        "## Negative results / limitations\n\n"
        + "\n".join(f"- {item['description']}" for item in negative)
        + "\n\nNo synthetic-to-real performance claim is made.\n",
        encoding="utf-8",
    )


def run_evaluation() -> dict[str, Any]:
    splits = _read_json(SEED_SPLITS_PATH)
    registry = _read_json(VERSION_REGISTRY_PATH)
    thresholds = _read_json(THRESHOLDS_PATH)
    seed_results: dict[str, list[dict[str, Any]]] = {}
    for split in ("development", "validation", "held_out"):
        seed_results[split] = [_evaluate_seed(seed) for seed in splits[split]]

    held_out = seed_results["held_out"]
    unseen = [_evaluate_unseen(seed) for seed in splits["held_out"]]
    held_metrics = _aggregate(held_out, unseen)

    current_config = DetectorConfig.load()
    legacy_config = replace(current_config, version="spc-ewma-v0.9.0-comparison", excursion_yield_threshold=0.82)
    legacy_results = [_evaluate_detector_only(seed, legacy_config) for seed in splits["held_out"]]
    legacy_fault_recall = round(mean(result["fault_recall"] for result in legacy_results), 5)

    summary: dict[str, Any] = {
        "evidence_schema_version": "m5-evaluation-v1",
        "seed_splits": splits,
        "version_registry": registry,
        "seed_results": seed_results,
        "unseen_family_results": unseen,
        "held_out_metrics": held_metrics,
        "common_random_number_comparison": {
            "seeds": splits["held_out"],
            "current_detector": {"version": current_config.version, "fault_recall": held_metrics["detector"]["fault_recall"]},
            "legacy_detector": {"version": legacy_config.version, "fault_recall": legacy_fault_recall},
        },
        "negative_results": [
            {
                "id": "NEG-001",
                "description": f"Contradicting-evidence coverage is {held_metrics['rca']['contradicting_evidence_coverage']:.3f}; not every correct candidate has explicit counter-evidence in the compact synthetic fixture.",
            },
            {
                "id": "NEG-002",
                "description": f"Legacy comparison detector recall is {legacy_fault_recall:.3f} on the same held-out random streams; it is retained as a failing/weaker baseline rather than hidden.",
            },
        ],
        "claims_boundary": {
            "real_public": "No real public dataset is used in M5 scoring; public datasets remain semantic/reality anchors.",
            "synthetic": "F1-F6 held-out scoring uses FabTwin-Sim test-profile traces.",
            "inferred": "Cases, RCA candidates and advisory text are deterministic inferred outputs.",
            "not_claimed": "No real-fab, Samsung, synthetic-to-real or production-control performance is claimed.",
        },
    }
    summary["release_gate"] = evaluate_thresholds(summary, thresholds)
    summary["release_passed"] = all(item["passed"] for item in summary["release_gate"])
    summary["canonical_hash"] = canonical_hash({key: value for key, value in summary.items() if key != "canonical_hash"})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic FabOps held-out release evaluation")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "release")
    parser.add_argument("--check", action="store_true", help="return non-zero if any release threshold fails")
    args = parser.parse_args()
    summary = run_evaluation()
    _write_reports(args.output, summary)
    print(json.dumps({"release_passed": summary["release_passed"], "canonical_hash": summary["canonical_hash"], "held_out_metrics": summary["held_out_metrics"]}, indent=2, sort_keys=True))
    if args.check and not summary["release_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
