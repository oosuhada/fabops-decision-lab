from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _score(predictions: dict[str, dict[str, Any]], target: str) -> float | None:
    item = predictions.get(target)
    if not item:
        return None
    try:
        return float(item.get("score"))
    except (TypeError, ValueError):
        return None


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _prediction_map(predictions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in predictions:
        target = str(item.get("target") or "")
        if target and target not in result:
            result[target] = item
    return result


def build_live_decision_intelligence(
    packet: dict[str, Any],
    predictions: list[dict[str, Any]],
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate learned predictions into bounded, operational decision support.

    The result deliberately does not mutate the deterministic recommendation or
    case state. It answers the more useful operational questions: why this case
    matters now, what should be checked next, what time horizon matters, and what
    concrete threshold would justify escalating the human review.
    """

    by_target = _prediction_map(predictions)
    predicted_yield = _score(by_target, "yield")
    excursion = _score(by_target, "excursion_probability")
    failure = _score(by_target, "future_failure_probability")
    maintenance = _score(by_target, "maintenance_probability")
    yield_deficit = max(0.0, 0.90 - predicted_yield) / 0.20 if predicted_yield is not None else 0.0
    risk_components = [value for value in (excursion, failure, maintenance, min(1.0, yield_deficit)) if value is not None]
    priority_score = max(risk_components or [min(1.0, float(packet.get("evidence", {}).get("anomaly_score", 0.0)) / 3.0)])

    classification = str(packet.get("classification") or "unknown")
    lot_id = str(packet.get("lot_id") or "unknown")
    chambers = list(packet.get("evidence", {}).get("affected_scope", {}).get("chambers", []))
    equipment = list(packet.get("evidence", {}).get("affected_scope", {}).get("equipment", []))
    primary_chamber = chambers[0] if chambers else "affected chamber"
    primary_equipment = equipment[0] if equipment else "affected equipment"

    if failure is not None and failure >= 0.75:
        signal = "ESCALATE_REVIEW"
        urgency = "HIGH"
        headline = f"{lot_id}: 다음 LOT 실패 위험 {_percent(failure)} — 선제 검토 필요"
        dominant_reason = f"next-lot failure model이 {_percent(failure)}로 HIGH 구간에 진입했습니다."
    elif excursion is not None and excursion >= 0.70:
        signal = "VERIFY_PHYSICAL"
        urgency = "HIGH"
        headline = f"{lot_id}: 공정 이상 위험 {_percent(excursion)} — 물리 근거 확인 우선"
        dominant_reason = f"excursion model이 {_percent(excursion)}로 물리 이상 가능성을 높게 보고 있습니다."
    elif maintenance is not None and maintenance >= 0.65:
        signal = "MAINTENANCE_WATCH"
        urgency = "WATCH"
        headline = f"{lot_id}: 유지보수 위험 {_percent(maintenance)} — 장비 상태 확인 필요"
        dominant_reason = f"maintenance model이 {_percent(maintenance)}로 다음 LOT 전 점검 필요성을 시사합니다."
    elif predicted_yield is not None and predicted_yield < 0.86:
        signal = "YIELD_WATCH"
        urgency = "WATCH"
        headline = f"{lot_id}: 예상 수율 {_percent(predicted_yield)} — 수율 저하 추세 확인"
        dominant_reason = f"학습형 yield forecast가 {_percent(predicted_yield)}로 90% 기준보다 낮습니다."
    elif classification == "data_quality_incident":
        signal = "VERIFY_DATA"
        urgency = "WATCH"
        headline = f"{lot_id}: 데이터 무결성 우선 — 공정 판단 보류"
        dominant_reason = "현재 케이스는 data-quality incident로 분류되어 공정 원인 판단보다 데이터 경로 검증이 우선입니다."
    else:
        signal = "MONITOR"
        urgency = "NORMAL"
        headline = f"{lot_id}: 현재 위험은 관리 범위 — 변화 감시 지속"
        dominant_reason = "학습형 모델에서 즉시 escalation 기준을 넘는 신호는 아직 없습니다."

    why_now = [dominant_reason]
    if predicted_yield is not None:
        why_now.append(f"예상 수율 {_percent(predicted_yield)} · 목표 90% 대비 {(0.90 - predicted_yield) * 100:+.1f}pp")
    if excursion is not None:
        why_now.append(f"공정 excursion 위험 {_percent(excursion)}")
    if failure is not None:
        why_now.append(f"다음 LOT failure 위험 {_percent(failure)}")
    if maintenance is not None:
        why_now.append(f"다음 LOT maintenance 필요 위험 {_percent(maintenance)}")

    next_actions: list[dict[str, str]] = []
    if classification == "data_quality_incident":
        next_actions.extend(
            [
                {"action": "이벤트 전달 순서와 누락 여부 재검증", "target": lot_id, "purpose": "공정 판단 전에 source truth를 복구"},
                {"action": "동일 시간대 인접 LOT과 source timestamp 비교", "target": "최근 3 LOT", "purpose": "단일 LOT 문제인지 ingestion 문제인지 구분"},
            ]
        )
    else:
        next_actions.append(
            {
                "action": f"{primary_chamber}의 최근 센서 추세와 직전 3 LOT 비교",
                "target": primary_chamber,
                "purpose": "현재 이상이 일시적 spike인지 누적 drift인지 구분",
            }
        )
        if failure is not None and failure >= 0.60:
            next_actions.append(
                {
                    "action": f"{primary_equipment}의 alarm / maintenance sequence 검토",
                    "target": primary_equipment,
                    "purpose": "다음 LOT failure precursor 확인",
                }
            )
        if predicted_yield is not None and predicted_yield < 0.90:
            next_actions.append(
                {
                    "action": "추가 metrology 결과를 현재 yield forecast와 비교",
                    "target": lot_id,
                    "purpose": "예측된 수율 저하가 실제 inspection으로 재현되는지 확인",
                }
            )
        if not next_actions:
            next_actions.append(
                {
                    "action": "다음 LOT prediction 변화를 감시",
                    "target": "next 1–3 lots",
                    "purpose": "risk band 전환 여부 확인",
                }
            )

    trigger_conditions = [
        {
            "condition": "future_failure_probability >= 0.80",
            "meaning": "다음 LOT 실패 위험이 80% 이상이면 human containment review 준비",
            "current": failure,
            "met": bool(failure is not None and failure >= 0.80),
        },
        {
            "condition": "excursion_probability >= 0.75",
            "meaning": "공정 excursion 위험이 75% 이상이면 추가 물리 계측을 최우선으로 전환",
            "current": excursion,
            "met": bool(excursion is not None and excursion >= 0.75),
        },
        {
            "condition": "predicted_yield < 0.85",
            "meaning": "예상 수율이 85% 아래면 다음 LOT 투입 전 검토 우선순위를 HIGH로 상향",
            "current": predicted_yield,
            "met": bool(predicted_yield is not None and predicted_yield < 0.85),
        },
    ]

    brief = report.get("brief", {}) if isinstance(report, dict) else {}
    llm_summary = None
    if isinstance(brief, dict):
        llm_summary = brief.get("summary") or brief.get("headline")

    return {
        "schema_version": "fabops-live-decision-intelligence-v1",
        "signal": signal,
        "urgency": urgency,
        "priority_score": round(float(priority_score), 6),
        "headline": headline,
        "why_now": why_now[:5],
        "next_actions": next_actions[:3],
        "trigger_conditions": trigger_conditions,
        "watch_horizon": "next 1–3 lots",
        "predictions": {
            "yield": predicted_yield,
            "excursion_probability": excursion,
            "future_failure_probability": failure,
            "maintenance_probability": maintenance,
        },
        "llm": {
            "provider": report.get("provider") if isinstance(report, dict) else None,
            "mode": report.get("mode") if isinstance(report, dict) else None,
            "summary": llm_summary,
            "generated_at": brief.get("generated_at") if isinstance(brief, dict) else None,
        },
        "authority": "decision-support-only",
        "equipment_control": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
