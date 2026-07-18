"""Film-cooled fluid-domain topology: box plenums + cylindrical holes + passage.

Pure-Python geometry consumed by build_film_layout, concept plots, and the
SpaceClaim journal.  The CAD model is a single merged fluid body:

  mainstream passage  ∪  box coolant chambers  ∪  cylindrical film holes

Holes extend slightly into the passage and plenum boxes so boolean merge does
not rely on face-to-face contact alone.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

# Hole diameters of overlap into adjacent fluid regions. The passage overlap is
# kept small: a shallow hole poked far into the passage grazes the curved wall
# and breaks the boolean union. The plenum overlap can be deeper (clean, the
# hole ends inside the box).
PASSAGE_OVERLAP_D = 0.30
PLENUM_OVERLAP_D = 0.50
PLENUM_DEPTH_D = 5.0
PLENUM_MARGIN_D = 2.0
PLENUM_NEAR_CLEARANCE_D = 0.75
LE_PLENUM_CENTER_OFFSET_D = 6.0
LE_PLENUM_HALF_LENGTH_D = 8.0
LE_PLENUM_RADIUS_D = 2.0


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n == 0:
        raise ValueError("zero-length vector")
    return v / n


def passage_outlet_mm(inst: dict, pitch_mm: float) -> np.ndarray:
    key = "passage_outlet_center_mm"
    if key in inst:
        return np.asarray(inst[key], dtype=float)
    outlet = np.asarray(inst["outlet_center_mm"], dtype=float)
    if inst.get("surface") == "pressure":
        outlet = outlet.copy()
        outlet[1] += pitch_mm
    return outlet


def passage_plenum_end_mm(inst: dict, pitch_mm: float) -> np.ndarray:
    key = "passage_plenum_end_center_mm"
    if key in inst:
        return np.asarray(inst[key], dtype=float)
    end = np.asarray(inst["plenum_end_center_mm"], dtype=float)
    if inst.get("surface") == "pressure":
        end = end.copy()
        end[1] += pitch_mm
    return end


def hole_axis_unit(inst: dict) -> np.ndarray:
    return _unit(np.asarray(inst["hole_axis_from_outlet_to_plenum"], dtype=float))


def cylinder_radius_point(start: np.ndarray, axis: np.ndarray, radius_mm: float) -> np.ndarray:
    """Return a point on the cylinder mantle (for SpaceClaim CylinderBody.Create)."""
    axis = _unit(axis)
    span = np.array([0.0, 0.0, 1.0])
    perp = np.cross(axis, span)
    if float(np.linalg.norm(perp)) < 1e-9:
        perp = np.cross(axis, np.array([1.0, 0.0, 0.0]))
    perp = _unit(perp)
    return start + radius_mm * perp


def hole_cylinder_mm(inst: dict, pitch_mm: float, *,
                     passage_overlap_d: float = PASSAGE_OVERLAP_D,
                     plenum_overlap_d: float = PLENUM_OVERLAP_D) -> dict[str, Any]:
    d = float(inst["diameter_mm"])
    r = 0.5 * d
    outlet = passage_outlet_mm(inst, pitch_mm)
    inner = passage_plenum_end_mm(inst, pitch_mm)
    axis = hole_axis_unit(inst)
    start = outlet - passage_overlap_d * d * axis
    end = inner + plenum_overlap_d * d * axis
    radius_pt = cylinder_radius_point(start, axis, r)
    return {
        "start_mm": [float(x) for x in start],
        "end_mm": [float(x) for x in end],
        "radius_mm": r,
        "radius_point_mm": [float(x) for x in radius_pt],
        "axis_unit": [float(x) for x in axis],
        "passage_overlap_d": passage_overlap_d,
        "plenum_overlap_d": plenum_overlap_d,
    }


def point_in_poly_xy(point: np.ndarray, poly: np.ndarray) -> bool:
    x, y = float(point[0]), float(point[1])
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_at_y = (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi
            if x < x_at_y:
                inside = not inside
        j = i
    return inside


def _box_corners_inside(lo, hi, blade_xy: np.ndarray) -> bool:
    corners = [
        (lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1]),
        (0.5 * (lo[0] + hi[0]), 0.5 * (lo[1] + hi[1])),
    ]
    return all(point_in_poly_xy(np.array(c), blade_xy) for c in corners)


def _profile_inside(profile_xy: np.ndarray, blade_xy: np.ndarray) -> bool:
    return all(point_in_poly_xy(np.asarray(p), blade_xy) for p in profile_xy)


def _bbox_from_profile(profile_xy: np.ndarray, span_hi_mm: float) -> tuple[np.ndarray, np.ndarray]:
    profile_xy = np.asarray(profile_xy, dtype=float)
    lo = np.array([float(np.min(profile_xy[:, 0])), float(np.min(profile_xy[:, 1])), 0.0])
    hi = np.array([float(np.max(profile_xy[:, 0])), float(np.max(profile_xy[:, 1])), float(span_hi_mm)])
    return lo, hi


def rounded_slot_profile_xy(
    center_xy: np.ndarray,
    axis_xy: np.ndarray,
    half_length_mm: float,
    radius_mm: float,
    *,
    n_arc: int = 16,
) -> np.ndarray:
    """Return a 2D capsule/rounded-slot polygon."""
    u = _unit(np.asarray(axis_xy, dtype=float))
    w = np.array([-u[1], u[0]])
    radius_mm = float(radius_mm)
    half_length_mm = max(float(half_length_mm), radius_mm)
    straight_half = max(half_length_mm - radius_mm, 0.0)
    c0 = np.asarray(center_xy, dtype=float) - straight_half * u
    c1 = np.asarray(center_xy, dtype=float) + straight_half * u

    pts: list[np.ndarray] = []
    for t in np.linspace(-math.pi / 2, math.pi / 2, n_arc):
        pts.append(c1 + radius_mm * (math.cos(t) * u + math.sin(t) * w))
    for t in np.linspace(math.pi / 2, 3 * math.pi / 2, n_arc):
        pts.append(c0 + radius_mm * (math.cos(t) * u + math.sin(t) * w))
    return np.asarray(pts)


def rounded_rect_profile_xy(
    base_xy: np.ndarray,
    u_xy: np.ndarray,
    v_xy: np.ndarray,
    half_u_mm: float,
    v_min_mm: float,
    v_max_mm: float,
    corner_radius_mm: float,
    *,
    n_corner: int = 6,
) -> np.ndarray:
    """Return an oriented rounded-rectangle polygon in local ``u``/``v`` axes."""
    u = _unit(np.asarray(u_xy, dtype=float))
    v = _unit(np.asarray(v_xy, dtype=float))
    base = np.asarray(base_xy, dtype=float)
    half_u = float(half_u_mm)
    v_min = float(v_min_mm)
    v_max = float(v_max_mm)
    width_v = max(v_max - v_min, 1e-9)
    r = min(float(corner_radius_mm), 0.45 * half_u, 0.45 * width_v)
    r = max(r, 1e-6)

    centers = [
        (half_u - r, v_min + r, -math.pi / 2, 0.0),
        (half_u - r, v_max - r, 0.0, math.pi / 2),
        (-half_u + r, v_max - r, math.pi / 2, math.pi),
        (-half_u + r, v_min + r, math.pi, 3 * math.pi / 2),
    ]
    pts: list[np.ndarray] = []
    for cu, cv, a0, a1 in centers:
        for t in np.linspace(a0, a1, n_corner):
            uu = cu + r * math.cos(t)
            vv = cv + r * math.sin(t)
            pts.append(base + uu * u + vv * v)
    return np.asarray(pts)


def plenum_slot_for_holes(
    items: list[dict],
    span_hi_mm: float,
    blade_xy: np.ndarray,
    *,
    depth_d: float = 4.0,
    near_clearance_d: float = PLENUM_NEAR_CLEARANCE_D,
    margin_d: float = PLENUM_MARGIN_D,
) -> dict[str, Any]:
    """Oriented rounded-slot plenum for one suction/pressure-side row group."""
    d_ref = float(max(item["diameter_mm"] for item in items))
    if "inlet_mm" in items[0]:
        anchors = np.array([item["inlet_mm"] for item in items], dtype=float)
    else:
        outlets = np.array([item["outlet_mm"] for item in items], dtype=float)
        axes = np.array([item["axis_unit"] for item in items], dtype=float)
        anchors = outlets + 3.35 * axes
    anchors_xy = anchors[:, :2]

    v = _unit(np.mean(np.array([item["axis_unit"][:2] for item in items], dtype=float), axis=0))
    if anchors_xy.shape[0] >= 2:
        centered = anchors_xy - anchors_xy.mean(axis=0)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        u = vh[0]
    else:
        u = np.array([-v[1], v[0]])
    if float(np.linalg.norm(u)) < 1e-9:
        u = np.array([-v[1], v[0]])
    u = _unit(u)

    base = anchors_xy.mean(axis=0)
    du = (anchors_xy - base) @ u
    dv = (anchors_xy - base) @ v
    row_half = float(np.max(np.abs(du))) if len(du) else 0.0

    def make_profile(depth_factor: float, near_factor: float, margin_factor: float):
        near_i = near_factor * d_ref
        depth_i = depth_factor * d_ref
        v_min = float(np.min(dv)) - near_i
        v_max = float(np.max(dv)) + depth_i
        half_length_i = row_half + margin_factor * d_ref
        radius_i = min(0.65 * d_ref, 0.25 * (v_max - v_min), 0.45 * half_length_i)
        center_i = base + 0.5 * (v_min + v_max) * v
        profile_i = rounded_rect_profile_xy(
            base, u, v, half_length_i, v_min, v_max, radius_i
        )
        return profile_i, center_i, near_i, depth_i, radius_i, half_length_i

    best = None
    for depth_factor in (depth_d, 3.5, 3.0, 2.5, 2.0):
        for near_factor in (near_clearance_d, 0.5, 0.25, 0.1):
            for margin_factor in (margin_d, 1.5, 1.0, 0.75, 0.5):
                profile_i, center_i, near_i, depth_i, radius_i, half_length_i = make_profile(
                    depth_factor, near_factor, margin_factor
                )
                if _profile_inside(profile_i, blade_xy):
                    best = (profile_i, center_i, near_i, depth_i, radius_i, half_length_i)
                    break
            if best is not None:
                break
        if best is not None:
            break
    if best is None:
        best = make_profile(2.0, 0.5, 0.5)

    profile, center, near, depth, radius, half_length = best
    lo, hi = _bbox_from_profile(profile, span_hi_mm)
    inlet_center = np.array([base[0], base[1], 0.5 * span_hi_mm]) + np.array([
        depth * v[0], depth * v[1], 0.0,
    ])
    inside = _profile_inside(profile, blade_xy)

    return {
        "shape": "oriented_rounded_slot",
        "profile_xy_mm": [[float(x), float(y)] for x, y in profile],
        "min_corner_mm": [float(x) for x in lo],
        "max_corner_mm": [float(x) for x in hi],
        "center_mm": [float(center[0]), float(center[1]), 0.5 * float(span_hi_mm)],
        "inlet_target_center_mm": [float(x) for x in inlet_center],
        "nominal_axis_from_holes_to_plenum": [float(v[0]), float(v[1]), 0.0],
        "row_axis_xy": [float(u[0]), float(u[1])],
        "depth_mm": float(depth),
        "near_clearance_mm": float(near),
        "half_length_mm": float(half_length),
        "radius_mm": float(radius),
        "corners_inside_blade": bool(inside),
    }


def leading_edge_plenum(
    blade_xy: np.ndarray,
    span_hi_mm: float,
    diameter_mm: float,
    *,
    pitch_shift_mm: float = 0.0,
) -> dict[str, Any]:
    """Fixed leading-edge capsule chamber for showerhead supply review."""
    xy = np.asarray(blade_xy, dtype=float)
    le = xy[int(np.argmin(xy[:, 0]))].copy()
    d = float(diameter_mm)
    center = le + np.array([LE_PLENUM_CENTER_OFFSET_D * d, pitch_shift_mm])
    profile = rounded_slot_profile_xy(
        center,
        np.array([0.0, 1.0]),
        LE_PLENUM_HALF_LENGTH_D * d,
        LE_PLENUM_RADIUS_D * d,
    )
    shifted_blade = xy + np.array([0.0, pitch_shift_mm])
    lo, hi = _bbox_from_profile(profile, span_hi_mm)
    inside = _profile_inside(profile, shifted_blade)
    return {
        "surface": "leading_edge",
        "connected_rows": ["LE1", "LE2", "LE3", "LE4", "LE5"],
        "shape": "leading_edge_capsule",
        "profile_xy_mm": [[float(x), float(y)] for x, y in profile],
        "min_corner_mm": [float(x) for x in lo],
        "max_corner_mm": [float(x) for x in hi],
        "center_mm": [float(center[0]), float(center[1]), 0.5 * float(span_hi_mm)],
        "inlet_target_center_mm": [
            float(center[0] + LE_PLENUM_RADIUS_D * d),
            float(center[1]),
            0.5 * float(span_hi_mm),
        ],
        "nominal_axis_from_holes_to_plenum": [1.0, 0.0, 0.0],
        "depth_mm": float(2.0 * LE_PLENUM_RADIUS_D * d),
        "half_length_mm": float(LE_PLENUM_HALF_LENGTH_D * d),
        "radius_mm": float(LE_PLENUM_RADIUS_D * d),
        "pitch_shift_mm": float(pitch_shift_mm),
        "corners_inside_blade": bool(inside),
    }


def plenum_box_for_holes(
    items: list[dict],
    span_hi_mm: float,
    blade_xy: np.ndarray,
    *,
    depth_d: float = PLENUM_DEPTH_D,
) -> dict[str, Any]:
    """Axis-aligned box plenum fully buried inside the blade solid.

    Anchored at the hole outlets and pushed inward along the mean inward normal
    to a depth where an axis-aligned box keeps every corner inside ``blade_xy``;
    this guarantees the plenum is sealed from the passage except via the holes.
    """
    d_ref = float(max(item["diameter_mm"] for item in items))
    outlets = np.array([item["outlet_mm"] for item in items], dtype=float)
    n_out = np.array([item["normal_out_xy"] for item in items], dtype=float)
    n_in_xy = -_unit(np.mean(n_out, axis=0))
    n_in = np.array([n_in_xy[0], n_in_xy[1], 0.0])
    base = outlets.mean(axis=0)

    best = None
    # Sweep depth (how far the box centre sits inside) and half-size; keep the
    # largest box whose footprint stays inside the blade.
    depth_grid = [d_ref * k for k in (depth_d, 4.0, 3.0, 2.5, 2.0, 1.5, 1.2, 1.0)]
    half_grid = [d_ref * k for k in (3.0, 2.5, 2.0, 1.5, 1.2, 1.0, 0.75, 0.6)]
    for depth_mm in depth_grid:
        center = base + depth_mm * n_in
        for half_mm in half_grid:
            lo = center - np.array([half_mm, half_mm, 0.0])
            hi = center + np.array([half_mm, half_mm, 0.0])
            lo[2], hi[2] = 0.0, float(span_hi_mm)
            if _box_corners_inside(lo, hi, blade_xy):
                best = (lo, hi, depth_mm, half_mm)
                break
        if best is not None:
            break
    if best is None:
        half_mm = 0.5 * d_ref
        center = base + 1.0 * d_ref * n_in
        lo = center - np.array([half_mm, half_mm, 0.0])
        hi = center + np.array([half_mm, half_mm, 0.0])
        lo[2], hi[2] = 0.0, float(span_hi_mm)
        best = (lo, hi, float(d_ref), half_mm)
    lo, hi, depth_mm, half_mm = best

    # Coolant supply face = the box face furthest into the blade along n_in.
    inlet_center = np.array([
        0.5 * (lo[0] + hi[0]), 0.5 * (lo[1] + hi[1]), 0.5 * (lo[2] + hi[2]),
    ])
    dominant = int(np.argmax(np.abs(n_in_xy)))
    inlet_center[dominant] = hi[dominant] if n_in_xy[dominant] >= 0 else lo[dominant]

    return {
        "shape": "axis_aligned_box",
        "min_corner_mm": [float(x) for x in lo],
        "max_corner_mm": [float(x) for x in hi],
        "center_mm": [0.5 * (lo[0] + hi[0]), 0.5 * (lo[1] + hi[1]),
                      0.5 * (lo[2] + hi[2])],
        "inlet_target_center_mm": [float(x) for x in inlet_center],
        "nominal_axis_from_holes_to_plenum": [float(x) for x in n_in],
        "depth_mm": float(depth_mm),
        "half_mm": float(half_mm),
        "corners_inside_blade": bool(_box_corners_inside(lo, hi, blade_xy)),
    }


def cylinder_into_plenum(outlet_mm, axis_unit, diameter_mm, plenum,
                         *, passage_overlap_d: float = PASSAGE_OVERLAP_D,
                         plenum_overlap_d: float = PLENUM_OVERLAP_D) -> dict[str, Any]:
    """Straight cylinder from the surface outlet to a point inside ``plenum``.

    Keeps the designed injection axis when that axis enters the box; otherwise
    aims at the box centre so the hole always connects passage -> plenum.
    """
    outlet = np.asarray(outlet_mm, dtype=float)
    design_axis = _unit(np.asarray(axis_unit, dtype=float))
    d = float(diameter_mm)
    r = 0.5 * d
    lo = np.asarray(plenum["min_corner_mm"], dtype=float)
    hi = np.asarray(plenum["max_corner_mm"], dtype=float)
    center = np.asarray(plenum["center_mm"], dtype=float)

    # Walk along the design axis; record the deepest sample that lands in the box.
    end = None
    max_reach = float(np.linalg.norm(center - outlet)) + np.linalg.norm(hi - lo)
    n_steps = 240
    for k in range(1, n_steps + 1):
        reach = max_reach * k / n_steps
        p = outlet + reach * design_axis
        if point_in_aabb(p, lo, hi):
            end = p  # keep extending while still inside -> deepest interior hit
        elif end is not None:
            break
    along_axis = end is not None
    if end is None:
        end = center.copy()
    tube_axis = _unit(end - outlet)
    start = outlet - passage_overlap_d * d * tube_axis
    end = end + plenum_overlap_d * d * tube_axis
    end = np.minimum(np.maximum(end, lo), hi)
    tube_axis = _unit(end - start)
    return {
        "start_mm": [float(x) for x in start],
        "end_mm": [float(x) for x in end],
        "radius_mm": r,
        "axis_unit": [float(x) for x in tube_axis],
        "design_axis_unit": [float(x) for x in design_axis],
        "aims_along_design_axis": bool(along_axis),
        "passage_overlap_d": passage_overlap_d,
        "plenum_overlap_d": plenum_overlap_d,
    }


def point_in_aabb(point: np.ndarray, lo: np.ndarray, hi: np.ndarray,
                  tol_mm: float = 1e-6) -> bool:
    return bool(np.all(point >= lo - tol_mm) and np.all(point <= hi + tol_mm))


def segment_exits_blade(start, end, blade_xy: np.ndarray, *, n: int = 64) -> bool:
    """True if the cylinder centerline crosses out of the blade between caps.

    Used to confirm the hole pierces the wall exactly once (passage -> plenum)
    rather than skimming back out into the passage.
    """
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    samples = [start + (end - start) * (k / n) for k in range(n + 1)]
    inside = [point_in_poly_xy(p[:2], blade_xy) for p in samples]
    transitions = sum(1 for i in range(len(inside) - 1) if inside[i] != inside[i + 1])
    return transitions > 1


def validate_instance_topology(inst: dict, plenum: dict, pitch_mm: float,
                               blade_xy: np.ndarray | None = None) -> dict[str, Any]:
    cyl = inst["cylinder_mm"]
    start = np.asarray(cyl["start_mm"], dtype=float)
    end = np.asarray(cyl["end_mm"], dtype=float)
    lo = np.asarray(plenum["min_corner_mm"], dtype=float)
    hi = np.asarray(plenum["max_corner_mm"], dtype=float)
    chk = {
        "id": inst["id"],
        "plenum_id": plenum["id"],
        "cylinder_end_inside_plenum": point_in_aabb(end, lo, hi),
        "cylinder_length_mm": float(np.linalg.norm(end - start)),
        "aims_along_design_axis": bool(cyl.get("aims_along_design_axis", True)),
    }
    if blade_xy is not None:
        chk["centerline_pierces_wall_once"] = not segment_exits_blade(start, end, blade_xy)
    return chk


def validate_layout_topology(layout: dict, pitch_mm: float,
                             blade_xy: dict[str, np.ndarray] | None = None) -> dict[str, Any]:
    plenum_by_surface = {p["surface"]: p for p in layout.get("plenums", [])}
    instance_checks = []
    ok = True
    for inst in layout.get("instances", []):
        plenum = plenum_by_surface.get(inst["surface"])
        if plenum is None:
            instance_checks.append({
                "id": inst["id"],
                "error": f"missing plenum for surface {inst['surface']}",
            })
            ok = False
            continue
        bxy = blade_xy.get(inst["surface"]) if blade_xy else None
        chk = validate_instance_topology(inst, plenum, pitch_mm, bxy)
        if not chk["cylinder_end_inside_plenum"]:
            ok = False
        if chk.get("centerline_pierces_wall_once") is False:
            ok = False
        instance_checks.append(chk)

    plenum_checks = []
    for plenum in layout.get("plenums", []):
        buried = bool(plenum.get("corners_inside_blade", False))
        if not buried:
            ok = False
        plenum_checks.append({"id": plenum["id"], "corners_inside_blade": buried})

    return {"ok": ok, "plenums": plenum_checks, "instances": instance_checks}
