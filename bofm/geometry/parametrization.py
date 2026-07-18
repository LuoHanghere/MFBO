"""Arc-length parametrization of the C3X vane surfaces.

Turns a design vector (per row: s/s0, p/D, alpha) into hole placements on the
2D vane profile (the vane is a constant cross-section extruded in span, so hole
positions live on the 2D contour; span array + injection tilt are applied on
top). This layer is pure-CPython and fully testable without any CAD tool; the
SpaceClaim journal just consumes the placements it produces.

Contour convention (configs/c3x_coordinates.csv, NASA CR-174827 Table II):
  index 0     -> leading edge (pt 1)
  index 0..29 -> one surface, LE -> TE (pt 1 .. pt 30)
  index 29..77-> other surface, TE -> LE (pt 30 .. pt 78)
Suction surface is the longer arc (177.82 mm); pressure the shorter (137.23 mm,
Table III) -- this is verified at load time and used to label the two surfaces.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

# Reference surface arc lengths (NASA CR-174827 Table III), for validation.
REF_SUCTION_ARC_MM = 177.82
REF_PRESSURE_ARC_MM = 137.23


@dataclass
class Surface:
    name: str                 # 'suction' | 'pressure'
    xy: np.ndarray            # (N, 2) polyline, LE -> TE
    s: np.ndarray             # (N,) cumulative arc length from LE [mm]

    @property
    def arc_mm(self) -> float:
        return float(self.s[-1])

    def locate(self, s_frac: float) -> tuple[float, float, float]:
        """Return (x_mm, y_mm, surface_tangent_angle_deg) at s/s0 = s_frac."""
        s_target = s_frac * self.arc_mm
        x = np.interp(s_target, self.s, self.xy[:, 0])
        y = np.interp(s_target, self.s, self.xy[:, 1])
        # local tangent via small central difference in arc length
        ds = max(self.arc_mm * 1e-3, 1e-4)
        s0, s1 = s_target - ds, s_target + ds
        dx = np.interp(s1, self.s, self.xy[:, 0]) - np.interp(s0, self.s, self.xy[:, 0])
        dy = np.interp(s1, self.s, self.xy[:, 1]) - np.interp(s0, self.s, self.xy[:, 1])
        return float(x), float(y), float(np.degrees(np.arctan2(dy, dx)))


def _cumulative_arc(xy: np.ndarray) -> np.ndarray:
    d = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
    return np.concatenate([[0.0], np.cumsum(d)])


def load_profile(csv_path: str | Path) -> np.ndarray:
    df = pd.read_csv(csv_path, comment="#")
    return df[["x_mm", "y_mm"]].to_numpy()


def clean_profile(profile: np.ndarray) -> np.ndarray:
    """Return profile points with the known C3X upper-TE kink point removed.

    The digitized C3X table has one point immediately before the trailing edge
    on the suction side that is almost vertically above the TE. Keeping it makes
    the interpolated upper trailing edge nearly vertical and visibly kinked.
    Drop only that very specific pattern: previous point has nearly the same x
    as the TE, while the y jump to the TE is large.
    """
    xy = np.asarray(profile, dtype=float).copy()
    if xy.shape[0] < 4:
        return xy
    _, te = find_le_te(xy)
    prev_i = (te - 1) % xy.shape[0]
    dx = abs(float(xy[prev_i, 0] - xy[te, 0]))
    dy = abs(float(xy[prev_i, 1] - xy[te, 1]))
    if dx < 0.25 and dy > 2.0:
        xy = np.delete(xy, prev_i, axis=0)
    return xy


def find_le_te(profile: np.ndarray) -> tuple[int, int]:
    """Leading edge = min axial x (nose); trailing edge = max axial x."""
    return int(np.argmin(profile[:, 0])), int(np.argmax(profile[:, 0]))


def _arc_indices(n: int, le: int, te: int, forward: bool) -> list[int]:
    """Indices from LE to TE around the closed contour (forward/backward)."""
    step = 1 if forward else -1
    idx, i = [le], le
    while i != te:
        i = (i + step) % n
        idx.append(i)
    return idx


def build_surfaces(profile: np.ndarray) -> dict[str, Surface]:
    """Split the closed contour into suction/pressure surfaces (both LE->TE).

    LE/TE are auto-detected (min/max axial x). The two arcs between them are the
    two surfaces; suction is the longer one.
    """
    n = profile.shape[0]
    le, te = find_le_te(profile)
    fwd = profile[_arc_indices(n, le, te, forward=True)].copy()
    bwd = profile[_arc_indices(n, le, te, forward=False)].copy()

    a = Surface("fwd", fwd, _cumulative_arc(fwd))
    b = Surface("bwd", bwd, _cumulative_arc(bwd))
    suction, pressure = (a, b) if a.arc_mm >= b.arc_mm else (b, a)
    suction.name, pressure.name = "suction", "pressure"
    return {"suction": suction, "pressure": pressure}


def validate_arcs(surfaces: dict[str, Surface], tol_mm: float = 3.0) -> dict[str, float]:
    """Compare computed surface arcs to NASA Table III; return abs errors [mm]."""
    err = {
        "suction": abs(surfaces["suction"].arc_mm - REF_SUCTION_ARC_MM),
        "pressure": abs(surfaces["pressure"].arc_mm - REF_PRESSURE_ARC_MM),
    }
    return err


@dataclass
class Hole:
    row_id: str
    surface: str
    s_frac: float
    x_mm: float
    y_mm: float
    tangent_deg: float        # surface tangent direction (LE->TE) in profile plane
    injection_deg: float      # streamwise inclination to surface
    p_over_D: float
    D_mm: float
    L_mm: float
    fixed: bool

    def streamwise_footprint_mm(self) -> float:
        """Approx surface breakout length of the inclined hole = D / sin(alpha)."""
        return self.D_mm / max(np.sin(np.radians(self.injection_deg)), 1e-3)


def place_holes(config: dict, surfaces: dict[str, Surface],
                design: dict | None = None) -> list[Hole]:
    """Build hole placements for all body rows.

    `design` (optional) overrides the baseline; it maps row_id -> dict with any
    of {s_over_s0, p_over_D, alpha_deg}. Missing keys fall back to baseline, so
    the optimizer can pass only the free variables.
    """
    dv = config["design_variables"]
    var = dv["variables"]
    s_base = var["arc_position_s_over_s0"]["baseline"]
    p_base = var["spacing_p_over_D"]["baseline"]
    a_base = var["injection_angle_alpha_deg"]["baseline"]
    surf_of = {r["id"]: r["surface"] for r in dv["rows"]}
    fixed_of = {r["id"]: r["fixed"] for r in dv["rows"]}
    body = config["geometry"]["body_rows"]
    D, L = float(body["hole_diameter_mm"]), float(body["hole_length_mm"])
    design = design or {}

    holes: list[Hole] = []
    for rid in s_base:
        d = design.get(rid, {})
        s_frac = float(d.get("s_over_s0", s_base[rid]))
        p_over_D = float(d.get("p_over_D", p_base[rid]))
        alpha = float(d.get("alpha_deg", a_base[rid]))
        surf = surfaces[surf_of[rid]]
        x, y, tan = surf.locate(s_frac)
        holes.append(Hole(rid, surf_of[rid], s_frac, x, y, tan,
                           alpha, p_over_D, D, L, fixed_of[rid]))
    return holes


def check_feasibility(holes: list[Hole], config: dict,
                      surfaces: dict[str, Surface]) -> list[str]:
    """Return a list of human-readable feasibility violations (empty == OK).

    Checks: variable bounds (s/s0 within baseline +/- 0.03, p/D and alpha within
    config bounds), within-surface ordering (preserve baseline order), and
    no row overlap (center spacing >= inclined-hole streamwise footprint).
    """
    var = config["design_variables"]["variables"]
    s_base = var["arc_position_s_over_s0"]["baseline"]
    s_half = 0.03  # bounds_rule: baseline +/- 0.03 in s/s0
    pD_lo, pD_hi = var["spacing_p_over_D"]["bounds"]
    a_lo, a_hi = var["injection_angle_alpha_deg"]["bounds"]

    v: list[str] = []
    for h in holes:
        if h.fixed:
            continue
        lo, hi = s_base[h.row_id] - s_half, s_base[h.row_id] + s_half
        if not (lo - 1e-9 <= h.s_frac <= hi + 1e-9):
            v.append(f"{h.row_id}: s/s0={h.s_frac:.3f} outside [{lo:.3f},{hi:.3f}]")
        if not (pD_lo - 1e-9 <= h.p_over_D <= pD_hi + 1e-9):
            v.append(f"{h.row_id}: p/D={h.p_over_D:.2f} outside [{pD_lo},{pD_hi}]")
        if not (a_lo - 1e-9 <= h.injection_deg <= a_hi + 1e-9):
            v.append(f"{h.row_id}: alpha={h.injection_deg:.1f} outside [{a_lo},{a_hi}]")

    by_surf: dict[str, list[Hole]] = defaultdict(list)
    for h in holes:
        by_surf[h.surface].append(h)
    for surf_name, hs in by_surf.items():
        if len(hs) < 2:
            continue
        arc = surfaces[surf_name].arc_mm
        expected = sorted(hs, key=lambda h: s_base[h.row_id])  # baseline order
        current = sorted(hs, key=lambda h: h.s_frac)
        if [h.row_id for h in expected] != [h.row_id for h in current]:
            v.append(f"{surf_name}: row ordering changed "
                     f"({[h.row_id for h in current]} vs baseline "
                     f"{[h.row_id for h in expected]})")
        for a, b in zip(current, current[1:]):
            sep_mm = (b.s_frac - a.s_frac) * arc
            need = 0.5 * (a.streamwise_footprint_mm() + b.streamwise_footprint_mm())
            if sep_mm < need:
                v.append(f"{surf_name}: {a.row_id}-{b.row_id} overlap "
                         f"(arc sep {sep_mm:.2f} mm < footprint {need:.2f} mm)")
    return v


def export_placements(holes: list[Hole], config: dict, path: str | Path,
                      profile: np.ndarray | None = None) -> Path:
    """Write a self-contained JSON the SpaceClaim journal consumes.

    If `profile` is given, the (x,y) contour is embedded so the journal needs no
    CSV parsing (one self-contained input).
    """
    geom = config["geometry"]
    payload = {
        "case": config["case"]["name"],
        "units": "mm / deg",
        "profile_csv": geom["airfoil_coordinates"],
        "span_mm": geom["span_mm"],
        "showerhead": geom["showerhead"],
        "body_rows_global": {k: geom["body_rows"][k] for k in
                             ("hole_diameter_mm", "hole_length_mm", "s_over_D",
                              "spanwise", "plenum")},
        "holes": [asdict(h) for h in holes],
    }
    if profile is not None:
        payload["profile_xy_mm"] = [[float(x), float(y)] for x, y in profile]
    path = Path(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
