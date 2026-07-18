"""Build a CAD/mesh-ready 3D film-hole layout from the design parameters.

The output is intentionally independent of SpaceClaim/Gmsh.  CAD journals and
mesh generators should consume this JSON instead of re-implementing the
optimization parameter mapping.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from bofm.geometry import parametrization as P
from bofm.geometry.film_topology import (
    cylinder_into_plenum,
    leading_edge_plenum,
    plenum_slot_for_holes,
    validate_layout_topology,
)
from bofm.geometry.profile import densify_profile


def _polygon_signed_area(xy: np.ndarray) -> float:
    x, y = xy[:, 0], xy[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _point_in_poly(point: np.ndarray, poly: np.ndarray) -> bool:
    x, y = point
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        crosses = (yi > y) != (yj > y)
        if crosses:
            x_at_y = (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi
            if x < x_at_y:
                inside = not inside
        j = i
    return inside


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n == 0:
        raise ValueError("zero-length vector")
    return v / n


def _surface_frame(hole: P.Hole, profile_xy: np.ndarray) -> dict:
    """Return local 2D tangent, outward normal, and injection direction."""
    theta = math.radians(hole.tangent_deg)
    tangent = _unit(np.array([math.cos(theta), math.sin(theta)]))

    # Two possible normals. Pick the one whose small offset leaves the solid.
    candidates = [
        _unit(np.array([-tangent[1], tangent[0]])),
        _unit(np.array([tangent[1], -tangent[0]])),
    ]
    p = np.array([hole.x_mm, hole.y_mm])
    outside = []
    for normal in candidates:
        outside.append(not _point_in_poly(p + 0.25 * normal, profile_xy))
    if outside[0] and not outside[1]:
        normal = candidates[0]
    elif outside[1] and not outside[0]:
        normal = candidates[1]
    else:
        # Fall back to polygon winding. This keeps the script deterministic if
        # the point is very close to a faceted edge.
        normal = candidates[0] if _polygon_signed_area(profile_xy) < 0 else candidates[1]

    alpha = math.radians(hole.injection_deg)
    jet_xy = _unit(math.cos(alpha) * tangent + math.sin(alpha) * normal)
    inlet_xy = -jet_xy
    return {
        "tangent_xy": tangent.tolist(),
        "outward_normal_xy": normal.tolist(),
        "forward_jet_direction_xy": jet_xy.tolist(),
        "forward_hole_axis_from_outlet_to_plenum_xy": inlet_xy.tolist(),
    }


def _span_centers(span_mm: float, pitch_mm: float, mode: str,
                  unit_span_mm: float | None = None) -> tuple[float, list[float]]:
    if mode == "unit-cell":
        effective = float(unit_span_mm) if unit_span_mm is not None else pitch_mm
        return effective, [0.5 * effective]

    n = max(1, int(math.floor(span_mm / pitch_mm)))
    if n == 1:
        return span_mm, [0.5 * span_mm]
    used = (n - 1) * pitch_mm
    first = 0.5 * (span_mm - used)
    return span_mm, [first + i * pitch_mm for i in range(n)]


def build_layout(config: dict, design: dict | None, mode: str,
                 unit_span_mm: float | None = None) -> dict:
    root = Path(__file__).resolve().parents[1]
    source_profile = P.load_profile(root / config["geometry"]["airfoil_coordinates"])
    raw_profile = P.clean_profile(source_profile)
    profile = densify_profile(raw_profile)
    surfaces = P.build_surfaces(profile)
    holes = P.place_holes(config, surfaces, design=design)
    violations = P.check_feasibility(holes, config, surfaces)

    span_mm = float(config["geometry"]["span_mm"])
    pitch_mm_cascade = float(config["geometry"]["pitch_mm"])
    rows = []
    unit_spans = []
    # First pass: hole geometry per spanwise instance, grouped per surface.
    hole_records: list[dict] = []
    plenum_groups: dict[str, list[dict]] = {"suction": [], "pressure": []}
    for row in holes:
        pitch_mm = row.p_over_D * row.D_mm
        effective_span_mm, z_centers = _span_centers(span_mm, pitch_mm, mode, unit_span_mm)
        unit_spans.append(effective_span_mm)
        frame = _surface_frame(row, profile)
        sense = str(config["geometry"]["body_rows"].get("injection_sense", "forward"))
        if design and row.row_id in design:
            sense = str(design[row.row_id].get("injection_sense", sense))
        if sense not in {"forward", "reverse"}:
            violations.append(f"{row.row_id}: invalid injection_sense={sense}")
            sense = "forward"
        tangent = np.array(frame["tangent_xy"])
        normal = np.array(frame["outward_normal_xy"])
        alpha = math.radians(row.injection_deg)
        sign = 1.0 if sense == "forward" else -1.0
        jet_xy = _unit(sign * math.cos(alpha) * tangent + math.sin(alpha) * normal)
        axis_to_plenum = -jet_xy
        outlet = np.array([row.x_mm, row.y_mm])
        inlet = outlet + row.L_mm * axis_to_plenum
        passage_shift = np.array([0.0, pitch_mm_cascade if row.surface == "pressure" else 0.0])
        passage_outlet = outlet + passage_shift
        passage_inlet = inlet + passage_shift

        row_payload = {
            **asdict(row),
            "injection_sense": sense,
            "span_pitch_mm": pitch_mm,
            "effective_span_mm": effective_span_mm,
            "n_holes": len(z_centers),
            **frame,
            "jet_direction_xy": jet_xy.tolist(),
            "hole_axis_from_outlet_to_plenum_xy": axis_to_plenum.tolist(),
        }
        rows.append(row_payload)

        for idx, z in enumerate(z_centers):
            rec = {
                "id": f"{row.row_id}_{idx:03d}",
                "row_id": row.row_id,
                "surface": row.surface,
                "z": float(z),
                "outlet": outlet,
                "inlet": inlet,
                "passage_outlet": np.array([passage_outlet[0], passage_outlet[1], z]),
                "passage_inlet": np.array([passage_inlet[0], passage_inlet[1], z]),
                "passage_shift": passage_shift,
                "axis": np.array([axis_to_plenum[0], axis_to_plenum[1], 0.0]),
                "jet": np.array([jet_xy[0], jet_xy[1], 0.0]),
                "normal_out": normal,
                "D": row.D_mm,
                "L": row.L_mm,
                "alpha": row.injection_deg,
                "sense": sense,
                "fixed": row.fixed,
            }
            hole_records.append(rec)
            plenum_groups[row.surface].append({
                "row_id": row.row_id,
                "outlet_mm": [float(passage_outlet[0]), float(passage_outlet[1]), float(z)],
                "inlet_mm": [float(passage_inlet[0]), float(passage_inlet[1]), float(z)],
                "axis_unit": [axis_to_plenum[0], axis_to_plenum[1], 0.0],
                "normal_out_xy": normal.tolist(),
                "diameter_mm": row.D_mm,
            })

    unique_unit_spans = sorted({round(v, 9) for v in unit_spans})
    span_hi = float(unique_unit_spans[0] if len(unique_unit_spans) == 1 else span_mm)

    # Buried box plenums (sealed from passage except through holes).
    blade_xy = {
        "suction": profile[:, :2],
        "pressure": profile[:, :2] + np.array([0.0, pitch_mm_cascade]),
    }
    plenums = []
    plenum_by_surface = {}
    for surface, items in plenum_groups.items():
        if not items:
            continue
        box = plenum_slot_for_holes(items, span_hi, blade_xy[surface])
        plenum = {
            "id": f"{surface}_plenum",
            "surface": surface,
            "connected_rows": sorted({item["row_id"] for item in items}),
            **box,
        }
        plenums.append(plenum)
        plenum_by_surface[surface] = plenum

    showerhead = config["geometry"].get("showerhead", {})
    if showerhead.get("fixed", False):
        d_le = float(showerhead.get("hole_diameter_mm", config["geometry"]["body_rows"]["hole_diameter_mm"]))
        le0 = leading_edge_plenum(profile[:, :2], span_hi, d_le, pitch_shift_mm=0.0)
        le0["id"] = "leading_edge_plenum"
        le0["surface"] = "leading_edge_lower"
        plenums.append(le0)

        le1 = leading_edge_plenum(profile[:, :2], span_hi, d_le, pitch_shift_mm=pitch_mm_cascade)
        le1["id"] = "leading_edge_plenum_periodic"
        le1["surface"] = "leading_edge_upper"
        plenums.append(le1)

    # Second pass: aim each cylinder from its surface outlet into the plenum.
    instances = []
    for rec in hole_records:
        plenum = plenum_by_surface[rec["surface"]]
        cyl = cylinder_into_plenum(
            rec["passage_outlet"], rec["axis"], rec["D"], plenum,
        )
        instances.append({
            "id": rec["id"],
            "row_id": rec["row_id"],
            "surface": rec["surface"],
            "outlet_center_mm": [float(rec["outlet"][0]), float(rec["outlet"][1]), rec["z"]],
            "plenum_end_center_mm": [float(rec["inlet"][0]), float(rec["inlet"][1]), rec["z"]],
            "passage_outlet_center_mm": [float(v) for v in rec["passage_outlet"]],
            "passage_plenum_end_center_mm": [float(v) for v in rec["passage_inlet"]],
            "passage_pitch_shift_mm": [float(rec["passage_shift"][0]), float(rec["passage_shift"][1]), 0.0],
            "jet_direction": [float(v) for v in rec["jet"]],
            "hole_axis_from_outlet_to_plenum": [float(v) for v in rec["axis"]],
            "diameter_mm": rec["D"],
            "length_mm": rec["L"],
            "span_pitch_mm": rec["D"] * next(r["p_over_D"] for r in rows if r["row_id"] == rec["row_id"]),
            "injection_angle_alpha_deg": rec["alpha"],
            "injection_sense": rec["sense"],
            "fixed": rec["fixed"],
            "cylinder_mm": cyl,
        })

    warnings = []
    if mode == "unit-cell" and len(unique_unit_spans) > 1:
        warnings.append(
            "unit-cell mode has multiple row pitches; use full-span or a supercell for independent p/D"
        )

    layout = {
        "case": config["case"]["name"],
        "units": "mm / deg",
        "mode": mode,
        "inspection_only": bool(unit_span_mm is not None and mode == "unit-cell"),
        "effective_span_mm": unique_unit_spans[0] if len(unique_unit_spans) == 1 else span_mm,
        "profile_points": {
            "source_raw": int(len(source_profile)),
            "cleaned_raw": int(len(raw_profile)),
            "densified": int(len(profile)),
        },
        "feasibility": violations or "OK",
        "warnings": warnings,
        "rows": rows,
        "plenums": plenums,
        "instances": instances,
    }
    layout["topology"] = validate_layout_topology(layout, pitch_mm_cascade, blade_xy)
    return layout


def plot_layout(config: dict, layout: dict, out_png: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    raw_profile = P.clean_profile(P.load_profile(root / config["geometry"]["airfoil_coordinates"]))
    dense = densify_profile(raw_profile)

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12, 7))
    for ax in (ax0,):
        ax.plot(np.append(dense[:, 0], dense[0, 0]),
                np.append(dense[:, 1], dense[0, 1]), color="0.65", lw=1.2)
        pitch = float(config["geometry"]["pitch_mm"])
        ax.plot(np.append(dense[:, 0], dense[0, 0]),
                np.append(dense[:, 1] + pitch, dense[0, 1] + pitch),
                color="0.82", lw=1.0)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("x [mm] axial")
        ax.set_ylabel("y [mm] tangential")

    colors = {
        "suction": "tab:red",
        "pressure": "tab:blue",
        "leading_edge_lower": "tab:green",
        "leading_edge_upper": "tab:green",
    }
    for row in layout["rows"]:
        x, y = row["x_mm"], row["y_mm"]
        if row["surface"] == "pressure":
            y += float(config["geometry"]["pitch_mm"])
        d = np.array(row["jet_direction_xy"])
        ax0.plot(x, y, "o", color=colors[row["surface"]], ms=8)
        ax0.arrow(x, y, 5.0 * d[0], 5.0 * d[1],
                  head_width=0.8, length_includes_head=True,
                  color=colors[row["surface"]])
        ax0.annotate(row["row_id"], (x, y), textcoords="offset points", xytext=(5, 5))
    for plenum in layout.get("plenums", []):
        color = colors.get(plenum["surface"], "tab:green")
        if "profile_xy_mm" in plenum:
            xy = np.asarray(plenum["profile_xy_mm"], dtype=float)
            rect_x = np.append(xy[:, 0], xy[0, 0])
            rect_y = np.append(xy[:, 1], xy[0, 1])
            cx, cy = np.mean(xy[:, 0]), np.mean(xy[:, 1])
        else:
            lo = plenum["min_corner_mm"]
            hi = plenum["max_corner_mm"]
            rect_x = [lo[0], hi[0], hi[0], lo[0], lo[0]]
            rect_y = [lo[1], lo[1], hi[1], hi[1], lo[1]]
            cx, cy = (lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5
        ax0.plot(rect_x, rect_y, "--", lw=1.3, color=color)
        ax0.annotate(plenum["id"], (cx, cy),
                     ha="center", va="center", fontsize=8,
                     color=color)
    for inst in layout.get("instances", []):
        cyl = inst.get("cylinder_mm")
        if not cyl:
            continue
        s = cyl["start_mm"]
        e = cyl["end_mm"]
        color = colors[inst["surface"]]
        ax0.plot([s[0], e[0]], [s[1], e[1]], "-", color=color, lw=1.4, alpha=0.85)
        ax0.plot(s[0], s[1], "o", color=color, ms=3)
    ax0.set_title("Film rows on C3X profile")

    by_row = {}
    for inst in layout["instances"]:
        by_row.setdefault(inst["row_id"], []).append(inst)
    ypos = np.arange(len(by_row))
    for yi, (rid, insts) in zip(ypos, by_row.items()):
        z = [p["outlet_center_mm"][2] for p in insts]
        ax1.scatter(z, [yi] * len(z), s=28)
    ax1.set_yticks(ypos, list(by_row.keys()))
    ax1.set_xlabel("z [mm] span")
    ax1.set_title(f"Spanwise holes ({layout['mode']})")
    ax1.grid(True, axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_png, dpi=130, bbox_inches="tight")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(root / "configs" / "c3x_baseline.yaml"))
    ap.add_argument("--mode", choices=["unit-cell", "full-span"], default="unit-cell")
    ap.add_argument("--unit-span-mm", type=float, default=None,
                    help="Inspection-only unit-cell span override; not for periodic solve")
    ap.add_argument("--out-json", default=str(root / "configs" / "c3x_film_layout_baseline.json"))
    ap.add_argument("--out-png", default=str(root / "configs" / "c3x_film_layout_baseline.png"))
    args = ap.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    layout = build_layout(config, design=None, mode=args.mode, unit_span_mm=args.unit_span_mm)
    out_json = Path(args.out_json)
    out_json.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    plot_layout(config, layout, Path(args.out_png))

    print("mode:", layout["mode"])
    print("effective span [mm]:", layout["effective_span_mm"])
    print("rows:", [(r["row_id"], r["n_holes"], round(r["span_pitch_mm"], 3)) for r in layout["rows"]])
    print("instances:", len(layout["instances"]))
    print("feasibility:", layout["feasibility"])
    print("topology ok:", layout.get("topology", {}).get("ok"))
    if layout["warnings"]:
        print("warnings:", layout["warnings"])
    print("wrote:", out_json)
    print("wrote:", args.out_png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
