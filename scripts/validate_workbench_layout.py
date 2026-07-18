"""Validate Route B Workbench film-hole layout before CAD/meshing.

This is a lightweight geometry gate for BO candidates.  It checks the layout JSON
written by ``build_c3x_workbench_case.py`` and can optionally verify downstream
hole inner endpoints against extracted plenum/cavity polygons.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from bofm.geometry.film_topology import point_in_poly_xy


SURFACE_TO_CAVITY = {
    "suction": "SS_plenum",
    "pressure": "PS_plenum",
    "leading_edge": "LE_plenum",
}


def _dist(a: list[float], b: list[float]) -> float:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    return float(np.linalg.norm(aa - bb))


def _point_segment_distance_xy(point: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom <= 1.0e-24:
        return float(np.linalg.norm(point - a))
    t = float(np.dot(point - a, ab) / denom)
    t = max(0.0, min(1.0, t))
    return float(np.linalg.norm(point - (a + t * ab)))


def _polygon_boundary_distance_xy(point: np.ndarray, polygon: np.ndarray) -> float:
    """Minimum XY distance from a point to a closed polygon boundary."""
    if len(polygon) < 2:
        return 0.0
    return min(
        _point_segment_distance_xy(point, polygon[i], polygon[(i + 1) % len(polygon)])
        for i in range(len(polygon))
    )


def _load_cavities(path: Path | None) -> dict[str, np.ndarray]:
    if path is None:
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for cav in doc.get("cavities", []):
        role = cav.get("role") or cav.get("name")
        poly = cav.get("profile_xy_mm")
        if role and poly:
            out[str(role)] = np.asarray(poly, dtype=float)
    return out


def _row_order_checks(rows: list[dict[str, Any]], min_gap_s_over_s0: float) -> list[dict[str, Any]]:
    issues = []
    by_surface: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_surface.setdefault(str(row.get("surface")), []).append(row)
    for surface, items in by_surface.items():
        ordered = sorted(items, key=lambda r: str(r.get("row_id")))
        vals = [float(r.get("s_over_s0", math.nan)) for r in ordered]
        ids = [str(r.get("row_id")) for r in ordered]
        for i in range(1, len(vals)):
            if not vals[i] > vals[i - 1]:
                issues.append({
                    "level": "error",
                    "kind": "row_order",
                    "surface": surface,
                    "message": f"{ids[i - 1]}={vals[i - 1]} is not upstream of {ids[i]}={vals[i]}",
                })
            elif vals[i] - vals[i - 1] < min_gap_s_over_s0:
                issues.append({
                    "level": "warning",
                    "kind": "row_spacing",
                    "surface": surface,
                    "message": f"{ids[i - 1]}->{ids[i]} spacing {vals[i] - vals[i - 1]:.6g} below {min_gap_s_over_s0}",
                })
    return issues


def validate_layout(
    layout: dict[str, Any],
    *,
    cavities: dict[str, np.ndarray] | None = None,
    min_marker_length_d: float = 1.0,
    min_gap_s_over_s0: float = 0.005,
    min_cavity_margin_d: float = 0.0,
) -> dict[str, Any]:
    cavities = cavities or {}
    rows = layout.get("rows", [])
    geom = layout.get("geometry", {})
    diameter = float(geom.get("diameter_mm", 0.0) or 0.0)
    span = float(geom.get("periodic_span_mm", 0.0) or 0.0)
    min_marker_length = min_marker_length_d * diameter if diameter > 0 else 0.0

    issues: list[dict[str, Any]] = []
    issues.extend(_row_order_checks(rows, min_gap_s_over_s0))

    row_summaries = []
    marker_count = 0
    cavity_checked = 0
    cavity_failed = 0
    cavity_clearances: list[float] = []

    for row in rows:
        row_id = str(row.get("row_id", "?"))
        surface = str(row.get("surface", "?"))
        checks = row.get("direction_checks", {})
        if checks:
            if checks.get("outside_probe_in_passage") is not True:
                issues.append({"level": "error", "kind": "direction", "row_id": row_id,
                               "message": "outside_probe_in_passage is not true"})
            if checks.get("inside_probe_in_blade") is not True:
                issues.append({"level": "error", "kind": "direction", "row_id": row_id,
                               "message": "inside_probe_in_blade is not true; hole may not enter blade/cavity side"})

        span_positions = [float(z) for z in row.get("span_positions_mm", [])]
        if span > 0:
            for z in span_positions:
                if not (0.0 < z < span):
                    issues.append({"level": "error", "kind": "span_position", "row_id": row_id,
                                   "message": f"span position {z} outside (0,{span})"})

        markers = row.get("cylinder_markers", [])
        if not markers:
            issues.append({"level": "error", "kind": "missing_markers", "row_id": row_id,
                           "message": "row has no cylinder_markers"})

        cavity_role = SURFACE_TO_CAVITY.get(surface)
        cavity_poly = cavities.get(cavity_role) if cavity_role else None

        lengths = []
        for marker in markers:
            marker_count += 1
            mid = marker.get("id", "?")
            start = marker.get("start_mm")
            end = marker.get("end_mm")
            radius = marker.get("radius_mm")
            if start is None or end is None or radius is None:
                issues.append({"level": "error", "kind": "bad_marker", "row_id": row_id,
                               "marker": mid, "message": "missing start/end/radius"})
                continue
            length = _dist(start, end)
            lengths.append(length)
            if length < min_marker_length:
                issues.append({"level": "error", "kind": "short_marker", "row_id": row_id,
                               "marker": mid, "message": f"length {length:.6g} mm below {min_marker_length:.6g} mm"})
            if cavity_poly is not None:
                cavity_checked += 1
                end_xy = np.asarray(end[:2], dtype=float)
                if not point_in_poly_xy(end_xy, cavity_poly):
                    cavity_failed += 1
                    issues.append({"level": "error", "kind": "cavity_miss", "row_id": row_id,
                                   "marker": mid, "cavity": cavity_role,
                                   "message": f"marker end {end_xy.tolist()} is outside {cavity_role}"})
                else:
                    clearance = _polygon_boundary_distance_xy(end_xy, cavity_poly)
                    cavity_clearances.append(clearance)
                    required = float(radius) + min_cavity_margin_d * diameter
                    if clearance < required:
                        cavity_failed += 1
                        issues.append({
                            "level": "error",
                            "kind": "cavity_clearance",
                            "row_id": row_id,
                            "marker": mid,
                            "cavity": cavity_role,
                            "clearance_mm": clearance,
                            "required_mm": required,
                            "message": (
                                f"marker end clearance {clearance:.6g} mm below "
                                f"cylinder requirement {required:.6g} mm"
                            ),
                        })

        row_summaries.append({
            "row_id": row_id,
            "surface": surface,
            "s_over_s0": row.get("s_over_s0"),
            "marker_count": len(markers),
            "marker_length_min_mm": min(lengths) if lengths else None,
            "marker_length_max_mm": max(lengths) if lengths else None,
        })

    error_count = sum(1 for i in issues if i["level"] == "error")
    warning_count = sum(1 for i in issues if i["level"] == "warning")
    return {
        "ok": error_count == 0,
        "error_count": error_count,
        "warning_count": warning_count,
        "marker_count": marker_count,
        "cavity_checked_markers": cavity_checked,
        "cavity_failed_markers": cavity_failed,
        "cavity_clearance_min_mm": min(cavity_clearances) if cavity_clearances else None,
        "cavity_clearance_required_mm": (
            0.5 * diameter + min_cavity_margin_d * diameter if diameter > 0 else None
        ),
        "rows": row_summaries,
        "issues": issues,
        "notes": [
            "This is a pre-CAD gate; it cannot replace a final Discovery/Fluent boundary-zone check.",
            "Cavity checks are only run when --cavities provides profile_xy_mm polygons.",
        ],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", required=True, help="Route B layout JSON from build_c3x_workbench_case.py")
    ap.add_argument("--cavities", default=None,
                    help="Optional cavity JSON with SS_plenum/PS_plenum polygons. "
                         "Use only when the cavity file is in the same coordinate frame "
                         "as the Route B layout.")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--min-marker-length-d", type=float, default=1.0)
    ap.add_argument("--min-gap-s-over-s0", type=float, default=0.005)
    ap.add_argument(
        "--min-cavity-margin-d",
        type=float,
        default=0.0,
        help="Additional cavity-wall clearance beyond the hole radius, in D",
    )
    args = ap.parse_args()

    layout = json.loads(Path(args.layout).read_text(encoding="utf-8"))
    cavities_path = None if args.cavities in (None, "", "none", "None") else Path(args.cavities)
    cavities = _load_cavities(cavities_path) if cavities_path and cavities_path.exists() else {}
    result = validate_layout(
        layout,
        cavities=cavities,
        min_marker_length_d=args.min_marker_length_d,
        min_gap_s_over_s0=args.min_gap_s_over_s0,
        min_cavity_margin_d=args.min_cavity_margin_d,
    )

    print("topology ok:", result["ok"])
    print("errors:", result["error_count"], "warnings:", result["warning_count"])
    print("markers:", result["marker_count"],
          "cavity checked:", result["cavity_checked_markers"],
          "cavity failed:", result["cavity_failed_markers"])
    for issue in result["issues"][:20]:
        print(issue["level"].upper(), issue["kind"], issue.get("row_id", ""), issue["message"])
    if len(result["issues"]) > 20:
        print("... additional issues:", len(result["issues"]) - 20)

    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("wrote:", out)

    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
