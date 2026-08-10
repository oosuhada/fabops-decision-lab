from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).parent / "configs"


@dataclass(frozen=True)
class SimulatorConfig:
    version: str
    profile: str
    simulated_days: int
    lot_count: int
    wafers_per_lot: int
    product_families: tuple[str, ...]
    process_steps: tuple[str, ...]
    equipment_per_step: int
    chambers_per_equipment: int
    sensors: tuple[str, ...]
    ar1_phi: float
    process_noise: float
    measurement_noise: float
    chamber_effect_std: float
    tool_aging_per_lot: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimulatorConfig":
        return cls(
            version=str(data["version"]),
            profile=str(data["profile"]),
            simulated_days=int(data["simulated_days"]),
            lot_count=int(data["lot_count"]),
            wafers_per_lot=int(data["wafers_per_lot"]),
            product_families=tuple(data["product_families"]),
            process_steps=tuple(data["process_steps"]),
            equipment_per_step=int(data["equipment_per_step"]),
            chambers_per_equipment=int(data["chambers_per_equipment"]),
            sensors=tuple(data["sensors"]),
            ar1_phi=float(data["ar1_phi"]),
            process_noise=float(data["process_noise"]),
            measurement_noise=float(data["measurement_noise"]),
            chamber_effect_std=float(data["chamber_effect_std"]),
            tool_aging_per_lot=float(data["tool_aging_per_lot"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile": self.profile,
            "simulated_days": self.simulated_days,
            "lot_count": self.lot_count,
            "wafers_per_lot": self.wafers_per_lot,
            "product_families": list(self.product_families),
            "process_steps": list(self.process_steps),
            "equipment_per_step": self.equipment_per_step,
            "chambers_per_equipment": self.chambers_per_equipment,
            "sensors": list(self.sensors),
            "ar1_phi": self.ar1_phi,
            "process_noise": self.process_noise,
            "measurement_noise": self.measurement_noise,
            "chamber_effect_std": self.chamber_effect_std,
            "tool_aging_per_lot": self.tool_aging_per_lot,
        }


def load_config(profile: str = "test") -> SimulatorConfig:
    path = CONFIG_DIR / f"{profile}.json"
    return SimulatorConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))

