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
    predicted_yield = _score(by_target, "final_yield")
    excursion = _score(by_target, "final_excursion_probability")
    next_lot_excursion_alarm = _score(by_target, "next_lot_excursion_alarm_probability")
    maintenance_attention = _score(by_target, "next_lot_maintenance_attention_probability")
    yield_deficit = max(0.0, 0.90 - predicted_yield) / 0.20 if predicted_yield is not None else 0.0

    classification = str(packet.get("classification") or "unknown")
    lot_id = str(packet.get("lot_id") or "unknown")
    chambers = list(packet.get("evidence", {}).get("affected_scope", {}).get("chambers", []))
    equipment = list(packet.get("evidence", {}).get("affected_scope", {}).get("equipment", []))
    primary_chamber = chambers[0] if chambers else "affected chamber"
    primary_equipment = equipment[0] if equipment else "affected equipment"

    probability_values = [value for value in (excursion, next_lot_excursion_alarm, maintenance_attention) if value is not None]
    calibrated_risk = max(probability_values, default=min(1.0, float(packet.get("evidence", {}).get("anomaly_score", 0.0)) / 3.0))
    anomaly_score = max(0.0, float(packet.get("evidence", {}).get("anomaly_score", 0.0)))
    severity = max(0.0, min(1.0, anomaly_score / 3.0))
    affected_scope = min(1.0, (len(chambers) + len(equipment)) / 6.0)
    persistence = min(1.0, anomaly_score / 4.0)
    uncertainty = (
        sum(1.0 - abs(value - 0.5) * 2.0 for value in probability_values) / len(probability_values)
        if probability_values
        else 0.5
    )
    actionability = 1.0 if chambers or equipment else 0.35
    yield_impact = min(1.0, yield_deficit)
    priority_components = {
        "calibrated_risk": round(calibrated_risk, 6),
        "severity": round(severity, 6),
        "affected_scope": round(affected_scope, 6),
        "persistence": round(persistence, 6),
        "yield_impact": round(yield_impact, 6),
        "uncertainty": round(uncertainty, 6),
        "human_actionability": round(actionability, 6),
    }
    priority_score = (
        calibrated_risk * 0.35
        + severity * 0.18
        + affected_scope * 0.12
        + persistence * 0.10
        + yield_impact * 0.15
        + uncertainty * 0.05
        + actionability * 0.05
    )

    if next_lot_excursion_alarm is not None and next_lot_excursion_alarm >= 0.75:
        signal = "ESCALATE_REVIEW"
        urgency = "HIGH"
        headline = f"{lot_id}: 다음 LOT excursion/alarm 위험 {_percent(next_lot_excursion_alarm)} — 선제 검토 필요"
        dominant_reason = f"next-lot excursion/alarm model이 {_percent(next_lot_excursion_alarm)}로 HIGH 구간에 진입했습니다. 실제 장비 failure 확률을 뜻하지 않습니다."
    elif excursion is not None and excursion >= 0.70:
        signal = "VERIFY_PHYSICAL"
        urgency = "HIGH"
        headline = f"{lot_id}: 공정 이상 위험 {_percent(excursion)} — 물리 근거 확인 우선"
        dominant_reason = f"excursion model이 {_percent(excursion)}로 물리 이상 가능성을 높게 보고 있습니다."
    elif maintenance_attention is not None and maintenance_attention >= 0.65:
        signal = "MAINTENANCE_WATCH"
        urgency = "WATCH"
        headline = f"{lot_id}: 유지보수 attention 위험 {_percent(maintenance_attention)} — 장비 상태 확인 필요"
        dominant_reason = f"maintenance-attention proxy가 {_percent(maintenance_attention)}로 다음 LOT 전 점검 우선순위를 높입니다. RUL 예측이 아닙니다."
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
        gap = (predicted_yield - 0.90) * 100
        direction = "높음" if gap >= 0 else "낮음"
        why_now.append(f"예상 수율 {_percent(predicted_yield)} · 목표 90% 대비 {abs(gap):.1f}pp {direction}")
    if excursion is not None:
        why_now.append(f"공정 excursion 위험 {_percent(excursion)}")
    if next_lot_excursion_alarm is not None:
        why_now.append(f"다음 LOT excursion/alarm 위험 {_percent(next_lot_excursion_alarm)} · equipment failure와 구분")
    if maintenance_attention is not None:
        why_now.append(f"다음 LOT maintenance attention 위험 {_percent(maintenance_attention)} · RUL 아님")

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
        if next_lot_excursion_alarm is not None and next_lot_excursion_alarm >= 0.60:
            next_actions.append(
                {
                    "action": f"{primary_equipment}의 alarm / maintenance sequence 검토",
                    "target": primary_equipment,
                    "purpose": "다음 LOT excursion/alarm precursor 확인",
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
                    "target": "next lot",
                    "purpose": "risk band 전환 여부 확인",
                }
            )

    trigger_conditions = [
        {
            "condition": "next_lot_excursion_alarm_probability >= 0.80",
            "meaning": "다음 LOT excursion/alarm 위험이 80% 이상이면 human containment review 준비",
            "current": next_lot_excursion_alarm,
            "met": bool(next_lot_excursion_alarm is not None and next_lot_excursion_alarm >= 0.80),
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
        "schema_version": "fabops-live-decision-intelligence-v2",
        "signal": signal,
        "urgency": urgency,
        "priority_score": round(float(priority_score), 6),
        "priority_components": priority_components,
        "headline": headline,
        "why_now": why_now[:5],
        "next_actions": next_actions[:3],
        "trigger_conditions": trigger_conditions,
        "watch_horizon": "next lot",
        "predictions": {
            "final_yield": predicted_yield,
            "final_excursion_probability": excursion,
            "next_lot_excursion_alarm_probability": next_lot_excursion_alarm,
            "next_lot_maintenance_attention_probability": maintenance_attention,
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
