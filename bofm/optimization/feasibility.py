"""Application-specific hard feasibility gates evaluated before CAD/CFD."""
from __future__ import annotations

import copy
import json
from pathlib import Path


class C3XDownstreamGeometryGate:
    """Use the production layout/plenum gate as an optimizer-side predicate."""

    def __init__(self, design_path: str | Path | None = None):
        root = Path(__file__).resolve().parents[2]
        self.root = root
        base_path = Path(design_path) if design_path else Path(
            "configs/c3x_downstream_design_baseline.json"
        )
        if not base_path.is_absolute():
            base_path = root / base_path
        self.base = json.loads(
            base_path.read_text(encoding="utf-8")
        )
        from scripts.validate_workbench_layout import _load_cavities

        self.cavities = _load_cavities(root / "configs/c3x_fixed_downstream_plenums.json")
        self.cache: dict[tuple, bool] = {}

    def __call__(self, design: dict[str, float | int]) -> bool:
        key = tuple(sorted((name, round(float(value), 10)) for name, value in design.items()))
        if key in self.cache:
            return self.cache[key]
        try:
            from scripts.build_c3x_downstream_layout import build_layout
            from scripts.validate_workbench_layout import validate_layout

            geometry = copy.deepcopy(self.base)
            for row in ("SS1", "SS2", "PS1", "PS2"):
                geometry["rows"][row]["s_over_s0"] = float(design[f"{row}_s"])
            for side in ("suction", "pressure"):
                geometry["surface_settings"][side]["injection_angle_deg"] = float(
                    design[f"{side}_angle_deg"]
                )
            if "diameter_mm" in design:
                geometry["geometry"]["diameter_mm"] = float(design["diameter_mm"])
            if "span_count" in design:
                geometry["geometry"]["span_count"] = int(design["span_count"])
            gate = validate_layout(
                build_layout(geometry),
                cavities=self.cavities,
                min_cavity_margin_d=0.25,
            )
            result = bool(gate["ok"])
        except Exception:
            result = False
        self.cache[key] = result
        return result


def build_geometry_gate(name: str | None):
    if not name:
        return None
    if name == "c3x_downstream":
        return C3XDownstreamGeometryGate()
    if name == "c3x_nasa44344":
        return C3XDownstreamGeometryGate(
            "runs/nasa_44344/geometry/c3x_nasa44344_periodic_v2_design.json"
        )
    raise ValueError(f"unknown geometry gate: {name}")
