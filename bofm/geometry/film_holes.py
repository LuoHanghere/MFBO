"""Parametric film-hole geometry: surface placement -> cylinder into a plenum.

Pure-Python. Turns row parameters (arc position, diameter, slant/skew angles,
spanwise pitch, target plenum) into the ``cylinder_mm`` segments the SpaceClaim
journal drills and booleans. Used for the FIXED leading-edge showerhead first;
the body rows reuse the same builder with optimised arc positions/angles.

Conventions (cascade CRS: x axial, y tangential, z span):
  - a row sits at signed arc length ``s`` from the LE stagnation: s>0 along the
    suction surface, s<0 along the pressure surface.
  - outward surface normal ``n_out`` is in the x-y plane; spanwise is +z.
  - hole axis INTO the wall (surface -> plenum):
        axis_in = sin(slant)*n_in + cos(slant)*(skew-rotated spanwise lean)
    slant = angle of the hole to the surface (90 deg = normal, 45 deg = NASA
    showerhead); skew = chordwise rotation of the lean (90 deg = pure spanwise
    lean, i.e. "normal in chordwise direction" per NASA Table IV).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .film_topology import point_in_poly_xy

# NASA CR-182133 Fig. 8 film-cooling hole reference points, in the vane (Fig. 7)
# coordinate frame: (U, V) in cm. 13-17 = the five LE showerhead rows, 11/12 =
# suction body rows, 18/19 = pressure body rows.
NASA_FILM_HOLES_UV_CM = {
    11: (3.592, 2.024), 12: (3.556, 1.631),
    13: (0.498, 0.541), 14: (0.211, 0.828), 15: (0.041, 1.196),
    16: (0.005, 1.600), 17: (0.109, 1.994),
    18: (0.559, 3.505), 19: (0.643, 3.891),
}
SHOWERHEAD_HOLE_IDS = [17, 16, 15, 14, 13]   # pressure-side -> LE -> suction-side

# NASA CR-182133 Fig. 8 RADIAL cooling holes (U, V) in cm. These 10 holes lie on
# the vane camber line spanning LE->TE, so they register the Fig.7 (U,V) frame to
# our cascade x-y far more robustly than the surface film holes do.
NASA_RADIAL_HOLES_UV_CM = {
    1: (2.870, 2.992), 2: (2.733, 3.998), 3: (2.555, 4.991), 4: (1.364, 4.788),
    5: (1.869, 6.182), 6: (1.666, 7.747), 7: (1.412, 9.235), 8: (1.087, 10.759),
    9: (0.737, 12.253), 10: (0.345, 13.757),
}


def fit_vane_to_cascade(surfaces):
    """Similarity transform (NASA vane Fig.7 U-V frame -> our cascade x-y, mm).

    Registered on the 10 RADIAL cooling holes, which lie on the camber line and
    span LE->TE, so the fit is well-constrained (no anchor guess). A similarity
    transform s*R*M (M = optional reflection) + t is least-squares fit so the
    radial holes land on our camber; reflection and rotation init are swept to
    avoid local minima. Returns uv_cm -> (x_mm, y_mm) plus fitted params.
    """
    suc = np.asarray(surfaces["suction"].xy, dtype=float)
    pre = np.asarray(surfaces["pressure"].xy, dtype=float)

    def rs(xy, n):
        f = np.linspace(0, 1, len(xy)); g = np.linspace(0, 1, n)
        return np.column_stack([np.interp(g, f, xy[:, 0]), np.interp(g, f, xy[:, 1])])
    # camber = medial line: each suction point paired with its NEAREST pressure
    # point (not by arc fraction, which skews near the LE where the arcs differ).
    sucr = rs(suc, 240); prer = rs(pre, 600)
    camber = np.array([0.5 * (p + prer[np.argmin(np.sum((prer - p) ** 2, axis=1))])
                       for p in sucr])
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(camber, axis=0), axis=1))])
    tau = arc / arc[-1]

    rad = np.array([NASA_RADIAL_HOLES_UV_CM[k] for k in range(1, 11)], dtype=float)
    SCALE = 10.0     # cm -> mm; rigid transform (no stretch)
    LE = np.asarray(suc[0], dtype=float)
    h16 = np.array(NASA_FILM_HOLES_UV_CM[16], dtype=float)   # stagnation = the LE

    # Anchor the stagnation showerhead row (hole 16) onto our LE -- the one
    # correspondence we are sure of. With scale fixed (rigid) and the anchor
    # fixing translation, only the rotation (+ reflection) is free: sweep it and
    # score by how well the 10 radial holes fall on the camber.
    # use ALL NASA holes to constrain the rotation: radial -> camber, showerhead
    # -> either surface, suction body (11,12) -> suction, pressure body (18,19)
    # -> pressure. This pulls out the systematic outward tilt a radial-only fit left.
    sh = np.array([NASA_FILM_HOLES_UV_CM[k] for k in (13, 14, 15, 17)], dtype=float)
    ssb = np.array([NASA_FILM_HOLES_UV_CM[k] for k in (11, 12)], dtype=float)
    psb = np.array([NASA_FILM_HOLES_UV_CM[k] for k in (18, 19)], dtype=float)
    surf_all = np.vstack([sucr, prer])

    def make(th, refl):
        c, si = math.cos(th), math.sin(th)
        A = SCALE * np.array([[c, -si], [si, c]]) @ np.array([[1.0, 0.0], [0.0, refl]])
        return A, (lambda uv: A @ (np.asarray(uv, dtype=float) - h16) + LE)

    def _d2(pts, ref):
        return float(np.sum([np.min(np.sum((ref - p) ** 2, axis=1)) for p in pts]))

    def score(T):
        return (_d2([T(uv) for uv in rad], camber)
                + _d2([T(uv) for uv in sh], surf_all)
                + _d2([T(uv) for uv in ssb], sucr)
                + _d2([T(uv) for uv in psb], prer))

    best = None
    for refl in (1.0, -1.0):
        for th in np.deg2rad(np.arange(0.0, 360.0, 0.5)):
            A, T = make(th, refl)
            sc = score(T)
            if best is None or sc < best[0]:
                best = (sc, th, refl, A)

    sc, th, refl, A = best
    _, T = make(th, refl)
    rms = (_d2([T(uv) for uv in rad], camber) / len(rad)) ** 0.5   # radial-only RMS
    return {"transform": T, "scale": SCALE,
            "angle_deg": float(math.degrees(th)),
            "reflection": float(refl), "rms_camber_mm": float(rms)}


def showerhead_arc_positions(surfaces):
    """Signed arc length from the LE for the 5 showerhead rows (NASA 17,16,15,14,13)."""
    suc = surfaces["suction"].xy
    pre = surfaces["pressure"].xy
    fit = fit_vane_to_cascade(surfaces)
    T = fit["transform"]
    out = []
    for hid in SHOWERHEAD_HOLE_IDS:
        q = T(NASA_FILM_HOLES_UV_CM[hid])
        ds = np.min(np.linalg.norm(suc - q, axis=1))
        dp = np.min(np.linalg.norm(pre - q, axis=1))
        surf = suc if ds < dp else pre
        sign = 1.0 if ds < dp else -1.0
        d = np.linalg.norm(np.diff(surf, axis=0), axis=1)
        cs = np.concatenate([[0.0], np.cumsum(d)])
        i = int(np.argmin(np.linalg.norm(surf - q, axis=1)))
        out.append({"nasa_hole": hid, "arc_s_mm": float(sign * cs[i]),
                    "cascade_xy_mm": [float(q[0]), float(q[1])]})
    return out, fit


def _arc_interp(xy: np.ndarray, s_target: float):
    """Point + unit tangent at arc length ``s_target`` from xy[0] (LE)."""
    xy = np.asarray(xy, dtype=float)
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    s_target = min(max(s_target, 0.0), float(s[-1]))
    i = int(np.searchsorted(s, s_target))
    i = min(max(i, 1), len(xy) - 1)
    t = (s_target - s[i - 1]) / (s[i] - s[i - 1] + 1e-12)
    p = xy[i - 1] + t * (xy[i] - xy[i - 1])
    tang = xy[i] - xy[i - 1]
    tang = tang / (np.linalg.norm(tang) + 1e-12)
    return p, tang


def surface_point_normal(surfaces, s_signed: float, interior_pt: np.ndarray):
    """Return (point_xy, outward_normal_xy) at signed arc length from the LE."""
    surf = surfaces["suction"] if s_signed >= 0 else surfaces["pressure"]
    p, tang = _arc_interp(surf.xy, abs(s_signed))
    n = np.array([-tang[1], tang[0]])
    if np.dot(n, p - interior_pt) < 0:          # orient away from the airfoil interior
        n = -n
    return p, n / (np.linalg.norm(n) + 1e-12)


def hole_axis_into_wall(n_out_xy: np.ndarray, slant_deg: float, skew_deg: float):
    """Unit 3D axis pointing surface -> plenum."""
    n_in = np.array([-n_out_xy[0], -n_out_xy[1], 0.0])
    # lean direction in the tangent plane: spanwise (+z) rotated by skew toward the
    # chordwise tangent. skew=90 deg -> pure spanwise; skew=0 -> chordwise.
    t_chord = np.array([n_out_xy[1], -n_out_xy[0], 0.0])   # surface tangent in x-y
    span = np.array([0.0, 0.0, 1.0])
    b = math.radians(skew_deg)
    lean = math.sin(b) * span + math.cos(b) * t_chord
    lean = lean / (np.linalg.norm(lean) + 1e-12)
    a = math.radians(slant_deg)
    axis = math.sin(a) * n_in + math.cos(a) * lean
    return axis / (np.linalg.norm(axis) + 1e-12)


def extend_into_plenum(start_xyz, axis, plenum_poly_xy, span_mm, *,
                       d_mm, passage_overlap_d=0.3, plenum_overlap_d=0.5,
                       max_reach_mm=40.0, n_steps=400):
    """March from start along axis; return (start, end, reached, z_lo, z_hi).

    Reach is an XY test (does the hole axis enter the plenum polygon): the slice
    is spanwise-PERIODIC, so z wrapping out of [0, span] is fine and only flagged
    (z_lo/z_hi) for the CAD periodic-split, not used to reject the connection."""
    start = np.asarray(start_xyz, dtype=float)
    axis = np.asarray(axis, dtype=float)
    poly = np.asarray(plenum_poly_xy, dtype=float)
    step = max_reach_mm / n_steps
    first_in = None
    for k in range(1, n_steps + 1):
        p = start + (step * k) * axis
        if point_in_poly_xy(p[:2], poly):
            first_in = p                       # stop at FIRST entry -> short duct
            break
    reached = first_in is not None
    end = first_in if reached else (start + max_reach_mm * 0.3 * axis)
    s0 = start - passage_overlap_d * d_mm * axis           # poke out of the surface
    e0 = end + plenum_overlap_d * d_mm * axis              # poke a bit into the plenum
    return s0, e0, reached, float(min(s0[2], e0[2])), float(max(s0[2], e0[2]))


def _cyl(start, end, d):
    start = [float(v) for v in start]
    end = [float(v) for v in end]
    r = 0.5 * float(d)
    axis = np.asarray(end) - np.asarray(start)
    axis = axis / (np.linalg.norm(axis) + 1e-12)
    span = np.array([0.0, 0.0, 1.0])
    perp = np.cross(axis, span)
    if np.linalg.norm(perp) < 1e-9:
        perp = np.cross(axis, np.array([1.0, 0.0, 0.0]))
    perp = perp / (np.linalg.norm(perp) + 1e-12)
    rp = np.asarray(start) + r * perp
    return {"start_mm": start, "end_mm": end, "radius_mm": r,
            "radius_point_mm": [float(v) for v in rp],
            "axis_unit": [float(v) for v in axis]}


def showerhead_rows(surfaces, le_plenum_poly, *, diameter_mm, rows_s,
                    p_over_D, slant_deg, skew_deg, span_mm,
                    holes_per_row=1, z_base=None, nasa_holes=None):
    """Fixed LE showerhead drilled into LE_plenum. ``rows_s`` = signed arc length
    of each row from the LE (from NASA Fig.8 via showerhead_arc_positions).
    Returns a list of hole instances with cylinder_mm."""
    D = float(diameter_mm)
    P = float(p_over_D) * D                    # spanwise pitch
    interior = np.asarray(le_plenum_poly, dtype=float).mean(axis=0)
    rows = list(rows_s)
    if z_base is None:
        z_base = 0.5 * span_mm
    out = []
    for ri, s in enumerate(rows):
        p2, n_out = surface_point_normal(surfaces, s, interior)
        axis = hole_axis_into_wall(n_out, slant_deg, skew_deg)
        stagger = (P / 2.0) if (ri % 2 == 1) else 0.0
        for h in range(holes_per_row):
            z = z_base + stagger + (h - (holes_per_row - 1) / 2.0) * P
            start = np.array([p2[0], p2[1], z])
            s0, e0, reached, z_lo, z_hi = extend_into_plenum(
                start, axis, le_plenum_poly, span_mm, d_mm=D)
            out.append({
                "id": "LE%d_%d" % (ri + 1, h),
                "surface": "leading_edge",
                "row": ri + 1,
                "nasa_hole": (nasa_holes[ri] if nasa_holes else None),
                "arc_s_mm": float(s),
                "plenum": "LE_plenum",
                "diameter_mm": D,
                "slant_deg": float(slant_deg),
                "skew_deg": float(skew_deg),
                "surface_point_mm": [float(p2[0]), float(p2[1]), float(z)],
                "reaches_plenum": bool(reached),
                "z_range_mm": [z_lo, z_hi],
                "crosses_slice": bool(z_lo < 0.0 or z_hi > span_mm),
                "cylinder_mm": _cyl(s0, e0, D),
            })
    return out
