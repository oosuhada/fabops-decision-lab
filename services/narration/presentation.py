from __future__ import annotations

import re
from typing import Any

from .grounding import reference_allowed

PRESENTATION_BLOCK_TYPES = {
    "SummaryCard",
    "Checklist",
    "ComparisonCard",
    "EvidenceTable",
}

_BLOCK_KEYS = {
    "SummaryCard": {"type", "title", "body", "evidence_refs"},
    "Checklist": {"type", "title", "items", "evidence_refs"},
    "ComparisonCard": {"type", "title", "recommended_option_id", "options", "evidence_refs"},
    "EvidenceTable": {"type", "title", "candidate_id", "rows", "evidence_refs"},
}
_FORBIDDEN_EXECUTABLE_KEYS = {
    "html",
    "javascript",
    "script",
    "tool",
    "command",
    "cypher",
    "sql",
    "shell",
    "filesystem",
    "url",
    "href",
    "src",
    "provider",
    "model",
    "component",
}
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


def _section_refs(brief: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for section in brief.get("sections", []):
        for reference in section.get("evidence_refs", []):
            if reference not in refs:
                refs.append(reference)
    return refs


def _summary_block(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "SummaryCard",
        "title": brief["headline"],
        "body": brief["summary"],
        "evidence_refs": list(brief.get("citations", []))[:4],
    }


def _comparison_block(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "ComparisonCard",
        "title": "Decision trade-offs",
        "recommended_option_id": packet["recommended_option_id"],
        "options": [
            {
                "option_id": option["option_id"],
                "label": option["label"],
                "stance": option["stance"],
                "tradeoff": option["tradeoff"],
                "requires_human_approval": bool(option["requires_human_approval"]),
            }
            for option in packet["options"]
        ],
        "evidence_refs": ["decision.recommended_option_id", "decision.options"],
    }


def _checklist_block(packet: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    items = [
        {
            "label": section["title"],
            "detail": section["body"],
            "evidence_refs": list(section.get("evidence_refs", [])),
        }
        for section in brief.get("sections", [])
    ]
    boundary = packet.get("decision_boundary") or {}
    for condition in boundary.get("conditions", []):
        if condition.get("status") != "met":
            items.append(
                {
                    "label": str(condition.get("label", "Evidence condition")),
                    "detail": f"current={condition.get('current_value')} · required={condition.get('required')}",
                    "evidence_refs": list(condition.get("evidence_refs", [])),
                }
            )
    return {
        "type": "Checklist",
        "title": "Bounded engineering checks",
        "items": items[:8],
        "evidence_refs": _section_refs(brief)[:6],
    }


def _evidence_table_block(packet: dict[str, Any]) -> dict[str, Any]:
    candidate = packet.get("evidence", {}).get("top_candidate") or {}
    rows: list[dict[str, Any]] = []
    for kind, records in (
        ("support", candidate.get("supporting_evidence", [])),
        ("contradict", candidate.get("contradicting_evidence", [])),
    ):
        for index, record in enumerate(records[:5]):
            rows.append(
                {
                    "kind": kind,
                    "record_index": index,
                    "summary": str(record.get("type") or record.get("detail") or "evidence record"),
                }
            )
    return {
        "type": "EvidenceTable",
        "title": "Counter-evidence first" if any(row["kind"] == "contradict" for row in rows) else "Grounded evidence",
        "candidate_id": candidate.get("candidate_id"),
        "rows": sorted(rows, key=lambda row: 0 if row["kind"] == "contradict" else 1),
        "evidence_refs": ["rca.top_candidate", "rca.supporting_evidence", "rca.contradicting_evidence"],
    }


def build_presentation_spec(packet: dict[str, Any], brief: dict[str, Any], intent: str) -> dict[str, Any]:
    if intent in {"tradeoff_compare", "manager_summary", "decision_brief"} and brief.get("audience") == "manager":
        blocks = [_summary_block(brief), _comparison_block(packet)]
    elif intent == "tradeoff_compare":
        blocks = [_comparison_block(packet), _summary_block(brief)]
    elif intent == "counter_evidence":
        blocks = [_evidence_table_block(packet), _checklist_block(packet, brief)]
    else:
        blocks = [_checklist_block(packet, brief), _evidence_table_block(packet)]
    spec = {
        "schema_version": "presentation-spec-v1",
        "renderer_contract": "known-components-only",
        "case_id": packet["case_id"],
        "intent": intent,
        "blocks": blocks,
        "execution_capabilities": [],
    }
    validate_presentation_spec(packet, spec)
    return spec


def _walk_presentation(value: Any) -> list[tuple[str | None, Any]]:
    walked: list[tuple[str | None, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            walked.append((str(key), child))
            walked.extend(_walk_presentation(child))
    elif isinstance(value, list):
        for child in value:
            walked.extend(_walk_presentation(child))
    return walked


def _validate_no_executable_content(block: dict[str, Any]) -> None:
    for key, value in _walk_presentation(block):
        if key is not None and key.lower() in _FORBIDDEN_EXECUTABLE_KEYS:
            raise ValueError("presentation block contains a forbidden executable field")
        if isinstance(value, str) and (_HTML_TAG.search(value) or "javascript:" in value.lower()):
            raise ValueError("presentation block contains forbidden HTML or JavaScript content")


def _validate_comparison_block(packet: dict[str, Any], block: dict[str, Any]) -> None:
    if block.get("recommended_option_id") != packet["recommended_option_id"]:
        raise ValueError("presentation changed deterministic recommendation")
    expected_options = [
        {
            "option_id": option["option_id"],
            "label": option["label"],
            "stance": option["stance"],
            "tradeoff": option["tradeoff"],
            "requires_human_approval": bool(option["requires_human_approval"]),
        }
        for option in packet["options"]
    ]
    if block.get("options") != expected_options:
        raise ValueError("presentation changed deterministic decision options")


def _validate_checklist_refs(packet: dict[str, Any], block: dict[str, Any], referenced: set[str]) -> None:
    items = block.get("items")
    if not isinstance(items, list) or len(items) > 8:
        raise ValueError("presentation checklist items must be a bounded list")
    for item in items:
        if not isinstance(item, dict) or set(item) != {"label", "detail", "evidence_refs"}:
            raise ValueError("presentation checklist item schema mismatch")
        item_refs = item.get("evidence_refs")
        if not isinstance(item_refs, list) or any(not isinstance(reference, str) for reference in item_refs):
            raise ValueError("presentation checklist evidence_refs must be a list of strings")
        referenced.update(item_refs)


def validate_presentation_spec(packet: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema_version") != "presentation-spec-v1":
        raise ValueError("presentation schema_version mismatch")
    if spec.get("renderer_contract") != "known-components-only":
        raise ValueError("presentation renderer contract mismatch")
    if spec.get("case_id") != packet["case_id"]:
        raise ValueError("presentation changed case_id")
    if spec.get("execution_capabilities") != []:
        raise ValueError("presentation cannot declare execution capabilities")
    blocks = spec.get("blocks")
    if not isinstance(blocks, list) or not blocks or len(blocks) > 4:
        raise ValueError("presentation blocks must contain 1 to 4 known blocks")
    referenced: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") not in PRESENTATION_BLOCK_TYPES:
            raise ValueError("presentation contains an unknown block type")
        block_type = str(block["type"])
        if set(block) != _BLOCK_KEYS[block_type]:
            raise ValueError("presentation block schema mismatch")
        if not isinstance(block.get("title"), str) or not block["title"].strip():
            raise ValueError("presentation block title is required")
        references = block.get("evidence_refs", [])
        if not isinstance(references, list) or any(not isinstance(reference, str) for reference in references):
            raise ValueError("presentation evidence_refs must be a list of strings")
        referenced.update(references)
        _validate_no_executable_content(block)
        if block_type == "ComparisonCard":
            _validate_comparison_block(packet, block)
        elif block_type == "Checklist":
            _validate_checklist_refs(packet, block, referenced)
    unknown = {reference for reference in referenced if not reference_allowed(packet, reference)}
    if unknown:
        raise ValueError(f"presentation contains unknown evidence refs: {sorted(unknown)}")
    return spec

