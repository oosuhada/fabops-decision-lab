from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from services.decision import DecisionSupportService
from services.narration.service import NarrationService
from systems.api.app import app
from systems.api.runtime import build_local_runtime


class FakeProvider:
    name = "fake-grounded"

    def __init__(self, *, mutate_recommendation: bool = False) -> None:
        self.mutate_recommendation = mutate_recommendation

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        packet = payload["decision_packet"]
        recommendation = "not-allowed" if self.mutate_recommendation else packet["recommended_option_id"]
        return {
            "schema_version": "decision-brief-v1",
            "case_id": packet["case_id"],
            "audience": payload["audience"],
            "headline": "근거 기반 판단 요약",
            "summary": "현재 근거 범위에서 사람의 판단을 지원하는 요약입니다.",
            "recommended_option_id": recommendation,
            "sections": [
                {
                    "section_id": "decision",
                    "title": "판단",
                    "body": "결정론적 권고를 변경하지 않고 설명합니다.",
                    "evidence_refs": ["decision.recommended_option_id"],
                }
            ],
            "citations": ["decision.recommended_option_id"],
            "uncertainties": packet["uncertainties"],
            "limitations": ["synthetic only"],
        }


def test_decision_cockpit_prioritizes_decision_questions_without_equipment_control() -> None:
    runtime = build_local_runtime()
    cockpit = DecisionSupportService(runtime).cockpit()
    assert cockpit["queue"]
    assert cockpit["queue"][0]["priority_rank"] >= cockpit["queue"][-1]["priority_rank"]
    for packet in cockpit["queue"]:
        assert packet["decision_question"]
        assert packet["recommended_option_id"] in {option["option_id"] for option in packet["options"]}
        assert packet["provenance"]["equipment_control"] is False
        assert packet["impact"]["basis"].startswith("synthetic")


def test_grounded_narration_can_reword_but_cannot_change_recommendation() -> None:
    runtime = build_local_runtime()
    packet = DecisionSupportService(runtime).packet(runtime.case_repository.list_cases()[0]["case_id"])

    accepted = NarrationService([FakeProvider()]).generate(packet, "manager")
    assert accepted["mode"] == "llm"
    assert accepted["provider"] == "fake-grounded"
    assert accepted["recommended_option_id"] == packet["recommended_option_id"]

    rejected = NarrationService([FakeProvider(mutate_recommendation=True)]).generate(packet, "manager")
    assert rejected["mode"] == "deterministic_fallback"
    assert rejected["recommended_option_id"] == packet["recommended_option_id"]
    assert "ValueError" in rejected["fallback_reason"]


def test_grounded_narration_caches_same_packet_and_audience() -> None:
    runtime = build_local_runtime()
    packet = DecisionSupportService(runtime).packet(runtime.case_repository.list_cases()[0]["case_id"])
    provider = FakeProvider()
    service = NarrationService([provider])

    first = service.generate(packet, "manager")
    second = service.generate(packet, "manager")

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["recommended_option_id"] == packet["recommended_option_id"]


def test_api_exposes_decision_cockpit_and_deterministic_brief_by_default() -> None:
    app.state.runtime = build_local_runtime()
    client = TestClient(app)
    cockpit = client.get("/api/decision-cockpit")
    assert cockpit.status_code == 200
    first = cockpit.json()["queue"][0]

    brief = client.get(f"/api/cases/{first['case_id']}/decision-brief?audience=engineer")
    assert brief.status_code == 200
    payload = brief.json()
    assert payload["brief"]["mode"] == "deterministic_fallback"
    assert payload["brief"]["recommended_option_id"] == payload["packet"]["recommended_option_id"]
    assert "ground_truth" not in brief.text
