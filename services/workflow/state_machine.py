from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from services.ingestion.ports import CaseRepositoryPort
from services.observability.telemetry import TelemetryRecorder

POLICY_VERSION = "workflow-policy-v1.0.0"
ALLOWED_PROPOSAL_ROLES = {"process_engineer", "yield_engineer", "fde"}
ALLOWED_APPROVAL_ROLES = {"yield_lead", "process_lead", "quality_manager"}
FORBIDDEN_ACTION_TYPES = {"execute_equipment_control", "automatic_recipe_change", "physical_tool_mutation"}


class WorkflowError(RuntimeError):
    pass


class AuthorizationError(WorkflowError):
    pass


class InvalidTransitionError(WorkflowError):
    pass


@dataclass(frozen=True)
class ApprovalTokenIssuer:
    secret: bytes
    issuer: str = "fabops-local-policy"

    def issue(self, case_id: str, action_id: str, actor_id: str, role: str) -> str:
        payload = f"{POLICY_VERSION}:{case_id}:{action_id}:{actor_id}:{role}"
        digest = hmac.new(self.secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{self.issuer}.{digest}"


class CaseWorkflowService:
    def __init__(
        self,
        cases: CaseRepositoryPort,
        token_issuer: ApprovalTokenIssuer | None = None,
        clock: Callable[[], datetime] | None = None,
        proposal_timeout: timedelta = timedelta(hours=4),
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self.cases = cases
        self.token_issuer = token_issuer or ApprovalTokenIssuer(b"local-fixture-key-not-for-production")
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.proposal_timeout = proposal_timeout
        self.telemetry = telemetry

    def _get(self, case_id: str) -> dict[str, Any]:
        case = self.cases.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        return case

    def _audit(self, case_id: str, event: str, actor_id: str, role: str, details: dict[str, Any]) -> None:
        self.cases.append_audit(
            {
                "case_id": case_id,
                "event": event,
                "actor_id": actor_id,
                "role": role,
                "policy_version": POLICY_VERSION,
                "occurred_at": self.clock().isoformat(),
                "details": details,
            }
        )

    def request_evidence(self, case_id: str, actor_id: str, role: str, reason: str) -> dict[str, Any]:
        if role not in ALLOWED_PROPOSAL_ROLES | ALLOWED_APPROVAL_ROLES:
            raise AuthorizationError(f"role {role} cannot request evidence")
        case = self._get(case_id)
        if case["state"] not in {"detected", "evidence_requested", "proposed"}:
            raise InvalidTransitionError(f"cannot request evidence from {case['state']}")
        case["state"] = "evidence_requested"
        case["evidence_request"] = {"reason": reason, "requested_by": actor_id, "requested_at": self.clock().isoformat()}
        self.cases.upsert_case(case)
        self._audit(case_id, "case.evidence_requested", actor_id, role, {"reason": reason})
        if self.telemetry is not None:
            self.telemetry.emit("workflow.request_evidence", case_id=case_id, outcome="updated")
        return case

    def propose_action(
        self,
        case_id: str,
        actor_id: str,
        role: str,
        action_type: str,
        target: str,
        rationale: str,
    ) -> dict[str, Any]:
        if role not in ALLOWED_PROPOSAL_ROLES:
            raise AuthorizationError(f"role {role} cannot propose actions")
        if action_type in FORBIDDEN_ACTION_TYPES:
            raise AuthorizationError("actual equipment/recipe mutation is out of scope")
        case = self._get(case_id)
        if case["state"] not in {"detected", "evidence_requested", "rejected"}:
            raise InvalidTransitionError(f"cannot propose action from {case['state']}")
        action_id = "ACT-" + hashlib.sha256(
            f"{case_id}:{action_type}:{target}:{rationale}:{POLICY_VERSION}".encode("utf-8")
        ).hexdigest()[:16].upper()
        proposed_at = self.clock().isoformat()
        case["state"] = "proposed"
        case["proposed_action"] = {
            "action_id": action_id,
            "action_type": action_type,
            "target": target,
            "rationale": rationale,
            "proposed_by": actor_id,
            "proposed_at": proposed_at,
            "execution_scope": "proposal-only-no-equipment-mutation",
        }
        self.cases.upsert_case(case)
        self._audit(case_id, "action.proposed", actor_id, role, case["proposed_action"])
        if self.telemetry is not None:
            self.telemetry.emit("workflow.action_proposed", case_id=case_id, outcome="updated")
        return case

    def approve(self, case_id: str, actor_id: str, role: str, reason: str) -> dict[str, Any]:
        if role not in ALLOWED_APPROVAL_ROLES:
            raise AuthorizationError(f"role {role} cannot approve actions")
        case = self._get(case_id)
        if case["state"] != "proposed" or not case.get("proposed_action"):
            raise InvalidTransitionError("approval requires a proposed action")
        action_id = case["proposed_action"]["action_id"]
        token = self.token_issuer.issue(case_id, action_id, actor_id, role)
        case["state"] = "approved"
        case["approval"] = {
            "approval_token": token,
            "approved_by": actor_id,
            "role": role,
            "reason": reason,
            "approved_at": self.clock().isoformat(),
            "policy_version": POLICY_VERSION,
            "actual_equipment_execution": False,
        }
        self.cases.upsert_case(case)
        self._audit(case_id, "action.approved", actor_id, role, {"action_id": action_id, "reason": reason, "approval_token": token})
        if self.telemetry is not None:
            self.telemetry.emit("workflow.action_approved", case_id=case_id, policy_version=POLICY_VERSION, approval_token=token, outcome="updated")
        return case

    def reject(self, case_id: str, actor_id: str, role: str, reason: str) -> dict[str, Any]:
        if role not in ALLOWED_APPROVAL_ROLES:
            raise AuthorizationError(f"role {role} cannot reject actions")
        case = self._get(case_id)
        if case["state"] != "proposed":
            raise InvalidTransitionError("rejection requires a proposed action")
        case["state"] = "rejected"
        case["rejection"] = {"rejected_by": actor_id, "role": role, "reason": reason, "rejected_at": self.clock().isoformat()}
        self.cases.upsert_case(case)
        self._audit(case_id, "action.rejected", actor_id, role, {"reason": reason})
        if self.telemetry is not None:
            self.telemetry.emit("workflow.action_rejected", case_id=case_id, outcome="updated")
        return case

    def close(self, case_id: str, actor_id: str, role: str, outcome: str) -> dict[str, Any]:
        case = self._get(case_id)
        if case["state"] not in {"approved", "rejected", "manual_intervention"}:
            raise InvalidTransitionError(f"cannot close case from {case['state']}")
        case["state"] = "closed"
        case["closure"] = {"outcome": outcome, "closed_by": actor_id, "closed_at": self.clock().isoformat()}
        self.cases.upsert_case(case)
        self._audit(case_id, "case.closed", actor_id, role, {"outcome": outcome})
        if self.telemetry is not None:
            self.telemetry.emit("workflow.case_closed", case_id=case_id, workflow_outcome=outcome, outcome="updated")
        return case

    def check_timeouts(self) -> list[str]:
        now = self.clock()
        escalated: list[str] = []
        for case in self.cases.list_cases():
            action = case.get("proposed_action")
            if case["state"] != "proposed" or not action:
                continue
            proposed_at = datetime.fromisoformat(action["proposed_at"])
            if now - proposed_at >= self.proposal_timeout:
                case["state"] = "manual_intervention"
                case["compensation"] = {
                    "reason": "approval_timeout",
                    "automatic_equipment_action": False,
                    "required_next_step": "manual review",
                }
                self.cases.upsert_case(case)
                self._audit(case["case_id"], "case.manual_intervention", "workflow-timeout", "system", case["compensation"])
                escalated.append(case["case_id"])
        return escalated

