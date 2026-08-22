from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FaultTruth:
    fault_id: str
    family: str
    physical_fault: bool
    yield_impact: bool
    start_lot: int
    end_lot: int
    step_id: str | None
    equipment_id: str | None
    chamber_id: str | None
    product_family: str | None
    expected_defect_pattern: str | None
    causal_parent: str | None
    expected_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

