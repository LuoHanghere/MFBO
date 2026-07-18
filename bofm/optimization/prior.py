"""Correlation-informed prior used by both the surrogate and demo plant."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PriorParameters:
    c0: float = 0.68
    c1: float = 0.22
    c2: float = 0.82
    blowing_ratio: float = 1.0
    angle_sigma_deg: float = 18.0
    suction_weight: float = 0.56


class FilmCoolingPrior:
    """Area-integrated row correlation with Sellers superposition.

    This is intentionally a low-order prior, not a substitute for CFD. Its GP
    residual is expected to learn curvature, pressure-gradient, jet interaction,
    and fidelity bias omitted here.
    """

    def __init__(self, settings: dict | None = None):
        settings = settings or {}
        allowed = PriorParameters.__dataclass_fields__
        self.parameters = PriorParameters(
            **{key: float(value) for key, value in settings.items() if key in allowed}
        )
        self.span_mm = float(settings.get("periodic_span_mm", 14.85))
        self.surface_arcs = {
            "suction": float(settings.get("suction_arc_mm", 177.82)),
            "pressure": float(settings.get("pressure_arc_mm", 137.23)),
        }

    def __call__(self, design: dict[str, float | int]) -> float:
        diameter = float(design.get("diameter_mm", 0.99))
        span_count = max(int(design.get("span_count", 5)), 1)
        pitch_over_diameter = self.span_mm / span_count / diameter
        values = {}
        for surface, row_names, optimum in (
            ("suction", ("SS1_s", "SS2_s"), 35.0),
            ("pressure", ("PS1_s", "PS2_s"), 30.0),
        ):
            angle = float(design.get(f"{surface}_angle_deg", optimum))
            values[surface] = self._surface_average(
                [float(design[name]) for name in row_names],
                angle,
                optimum,
                diameter,
                pitch_over_diameter,
                self.surface_arcs[surface],
            )
        w = self.parameters.suction_weight
        return float(np.clip(w * values["suction"] + (1.0 - w) * values["pressure"], 0.0, 1.0))

    def _surface_average(
        self,
        row_positions: list[float],
        angle_deg: float,
        optimum_angle_deg: float,
        diameter_mm: float,
        pitch_over_diameter: float,
        arc_mm: float,
    ) -> float:
        p = self.parameters
        s = np.linspace(min(row_positions), 1.0, 600)
        total = np.zeros_like(s)
        slot_width = np.pi * diameter_mm / (4.0 * pitch_over_diameter)
        angle_factor = np.exp(-((angle_deg - optimum_angle_deg) / p.angle_sigma_deg) ** 2)
        for row in sorted(row_positions):
            downstream_mm = np.maximum((s - row) * arc_mm, 0.0)
            eta = p.c0 * angle_factor / (
                1.0 + p.c1 * (downstream_mm / max(p.blowing_ratio * slot_width, 1e-6)) ** p.c2
            )
            eta[s < row] = 0.0
            total = 1.0 - (1.0 - total) * (1.0 - np.clip(eta, 0.0, 0.98))
        return float(np.trapz(total, s) / max(1.0 - min(row_positions), 1e-9))
