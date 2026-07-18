"""Single-pitch periodic cascade passage for the C3X vane.

Builds the 2D blade-to-blade fluid passage between two adjacent blades
(blade_0 and blade_1 = blade_0 + pitch in the tangential y direction):

  walls    : suction side of blade_0 (lower) + pressure side of blade_1 (upper)
  inlet    : vertical plane at x_in, one pitch tall
  outlet   : plane at x_out, one pitch tall
  periodic : upstream/downstream extension lines; each lower segment + pitch
             equals the matching upper segment (translational periodicity)

The resulting closed loop is what the SpaceClaim journal sketches and extrudes
to span to get the fluid domain (no holes -> no-film validation case).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .parametrization import Surface


@dataclass
class Passage:
    loop_xy: np.ndarray                      # (N,2) closed outer boundary, CCW
    segments: dict[str, np.ndarray] = field(default_factory=dict)
    pitch_mm: float = 0.0
    x_in: float = 0.0
    x_out: float = 0.0


def build_passage(surfaces: dict[str, Surface], *, pitch_mm: float,
                  axial_chord_mm: float, up_chord: float = 1.0,
                  down_chord: float = 1.5, inlet_angle_deg: float = 0.0,
                  exit_angle_deg: float = 72.38) -> Passage:
    suc = surfaces["suction"].xy        # LE -> TE (lower-blade upper wall)
    pre = surfaces["pressure"].xy       # LE -> TE
    le = suc[0]
    te = suc[-1]

    x_in = le[0] - up_chord * axial_chord_mm
    x_out = te[0] + down_chord * axial_chord_mm
    pitch = np.array([0.0, pitch_mm])

    # upper-blade walls/points (blade_1 = blade_0 + pitch)
    pre_up = pre + pitch
    le1, te1 = le + pitch, te + pitch

    # exit_angle_deg: signed angle from +x (axial) toward +y (tangential).
    # NASA Table III reports air_exit_angle as a positive magnitude (72.38 deg);
    # in this CRS the mean exit flow turns toward -y (suction TE tangent ~ -76 deg),
    # so callers pass a negative value (e.g. -72.38).
    t = np.tan(np.radians(exit_angle_deg))
    ti = np.tan(np.radians(inlet_angle_deg))

    # periodic extension endpoints
    p_in_low = np.array([x_in, le[1] - (le[0] - x_in) * ti])
    p_in_up = p_in_low + pitch
    p_out_low = np.array([x_out, te[1] + (x_out - te[0]) * t])
    p_out_up = p_out_low + pitch

    segs = {
        "inlet": np.array([p_in_low, p_in_up]),
        "periodic_up_upper": np.array([p_in_up, le1]),
        "wall_blade1_pressure": pre_up,                 # LE1 -> TE1
        "periodic_down_upper": np.array([te1, p_out_up]),
        "outlet": np.array([p_out_up, p_out_low]),
        "periodic_down_lower": np.array([p_out_low, te]),
        "wall_blade0_suction": suc[::-1],               # TE -> LE
        "periodic_up_lower": np.array([le, p_in_low]),
    }
    loop = np.vstack([
        segs["inlet"],
        segs["periodic_up_upper"][1:],
        segs["wall_blade1_pressure"][1:],
        segs["periodic_down_upper"][1:],
        segs["outlet"][1:],
        segs["periodic_down_lower"][1:],
        segs["wall_blade0_suction"][1:],
        segs["periodic_up_lower"][1:],
    ])
    return Passage(loop, segs, pitch_mm, x_in, x_out)
