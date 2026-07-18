"""Build the variable downstream C3X hole layout from a compact design JSON."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from bofm.geometry.film_topology import point_in_poly_xy
from scripts.build_c3x_kumar_paper_layout import build_paper_surfaces, outward_normal


ROOT = Path(__file__).resolve().parents[1]
ROW_ORDER = ("SS1", "SS2", "PS1", "PS2")


def _validate_design(design: dict) -> None:
    geometry = design["geometry"]
    rows = design["rows"]
    settings = design["surface_settings"]
    if set(rows) != set(ROW_ORDER):
        raise ValueError("design must define exactly SS1, SS2, PS1, PS2")
    if rows["SS1"]["surface"] != "suction" or rows["SS2"]["surface"] != "suction":
        raise ValueError("SS rows must use the suction surface")
    if rows["PS1"]["surface"] != "pressure" or rows["PS2"]["surface"] != "pressure":
        raise ValueError("PS rows must use the pressure surface")
    for row_id in ROW_ORDER:
        s = float(rows[row_id]["s_over_s0"])
        if not 0.02 < s < 0.95:
            raise ValueError(f"{row_id} s_over_s0 is outside the usable surface")
    if not float(rows["SS1"]["s_over_s0"]) < float(rows["SS2"]["s_over_s0"]):
        raise ValueError("SS1 must be upstream of SS2")
    if not float(rows["PS1"]["s_over_s0"]) < float(rows["PS2"]["s_over_s0"]):
        raise ValueError("PS1 must be upstream of PS2")
    for surface in ("suction", "pressure"):
        if settings[surface]["orientation"] not in ("forward", "reverse"):
            raise ValueError(f"invalid {surface} orientation")
        angle = float(settings[surface]["injection_angle_deg"])
        if not 5.0 <= angle <= 85.0:
            raise ValueError(f"invalid {surface} injection angle")
    count = int(geometry["span_count"])
    if count != float(geometry["span_count"]) or count < 1:
        raise ValueError("span_count must be a positive integer")
    if float(geometry["diameter_mm"]) <= 0.0:
        raise ValueError("diameter_mm must be positive")


def build_layout(design: dict) -> dict:
    _validate_design(design)
    surfaces, profile, reconstruction = build_paper_surfaces()
    geometry = design["geometry"]
    diameter = float(geometry["diameter_mm"])
    radius = 0.5 * diameter
    hole_length = float(geometry["physical_hole_length_mm"])
    passage_overlap = float(geometry["passage_overlap_D"]) * diameter
    default_inner_overlap_D = float(geometry["inner_overlap_D"])
    inner_overlap_by_surface_D = geometry.get("inner_overlap_D_by_surface", {})
    span = float(geometry["periodic_span_mm"])
    span_count = int(geometry["span_count"])
    span_pitch = span / span_count
    phase = float(geometry.get("span_phase_fraction", 0.5))
    z_positions = (np.arange(span_count, dtype=float) + phase) * span_pitch
    if z_positions[0] - radius <= 0.0 or z_positions[-1] + radius >= span:
        raise ValueError("hole radius crosses a span-periodic boundary; adjust phase/count/diameter")

    shared_frames = {}
    for surface_name, row_ids in (("suction", ("SS1", "SS2")), ("pressure", ("PS1", "PS2"))):
        surface = surfaces[surface_name]
        center_fraction = sum(float(design["rows"][rid]["s_over_s0"]) for rid in row_ids) / 2.0
        center_s = center_fraction * surface.reference_arc_mm
        center_point, tangent = surface.locate_reference_arc(center_s)
        n_out = outward_normal(center_point, tangent, profile)
        spec = design["surface_settings"][surface_name]
        alpha = math.radians(float(spec["injection_angle_deg"]))
        stream_sign = 1.0 if spec["orientation"] == "forward" else -1.0
        exit_axis = stream_sign * math.cos(alpha) * tangent + math.sin(alpha) * n_out
        exit_axis /= np.linalg.norm(exit_axis)
        shared_frames[surface_name] = {
            "center_s_over_s0": center_fraction,
            "center_xy_mm": center_point.tolist(),
            "tangent_le_to_te": tangent.tolist(),
            "outward_normal_xy": n_out.tolist(),
            "coolant_exit_axis_xy": exit_axis.tolist(),
        }

    rows_out = []
    for row_id in ROW_ORDER:
        row = design["rows"][row_id]
        surface_name = row["surface"]
        inner_overlap_D = float(
            inner_overlap_by_surface_D.get(surface_name, default_inner_overlap_D)
        )
        inner_overlap = inner_overlap_D * diameter
        surface = surfaces[surface_name]
        s_fraction = float(row["s_over_s0"])
        s_ref = s_fraction * surface.reference_arc_mm
        point, tangent = surface.locate_reference_arc(s_ref)
        n_out = outward_normal(point, tangent, profile)
        exit_axis = np.asarray(shared_frames[surface_name]["coolant_exit_axis_xy"], dtype=float)
        into_axis = -exit_axis
        outside_ok = not point_in_poly_xy(point + 0.2 * diameter * exit_axis, profile)
        inside_ok = point_in_poly_xy(point + 0.2 * diameter * into_axis, profile)
        if not (outside_ok and inside_ok):
            raise ValueError(f"{row_id} shared axis does not cross the local wall correctly")
        start_xy = point + passage_overlap * exit_axis
        end_xy = point + (hole_length + inner_overlap) * into_axis
        markers = []
        for zi, z in enumerate(z_positions, 1):
            markers.append({
                "id": f"{row_id}_z{zi:02d}",
                "start_mm": [float(start_xy[0]), float(start_xy[1]), float(z)],
                "end_mm": [float(end_xy[0]), float(end_xy[1]), float(z)],
                "radius_mm": radius,
                "radius_vector_mm": [0.0, 0.0, radius],
            })
        rows_out.append({
            "row_id": row_id,
            "surface": surface_name,
            "source_nasa_hole": int(row["source_nasa_hole"]),
            "s_over_s0": s_fraction,
            "surface_arc_reference_mm": s_ref,
            "surface_xy_mm": point.tolist(),
            "local_tangent_le_to_te": tangent.tolist(),
            "local_outward_normal_xy": n_out.tolist(),
            "injection_angle_deg": float(design["surface_settings"][surface_name]["injection_angle_deg"]),
            "orientation": design["surface_settings"][surface_name]["orientation"],
            "inner_overlap_D": inner_overlap_D,
            "coolant_exit_axis_xy": exit_axis.tolist(),
            "surface_to_plenum_axis_xy": into_axis.tolist(),
            "shared_surface_frame": shared_frames[surface_name],
            "direction_checks": {"outside_probe_in_passage": outside_ok, "inside_probe_in_blade": inside_ok},
            "span_positions_mm": z_positions.tolist(),
            "cylinder_markers": markers,
        })
    return {
        "source_design": design,
        "units": "mm",
        "geometry": {
            "periodic_span_mm": span,
            "diameter_mm": diameter,
            "physical_hole_length_mm": hole_length,
            "marker_total_length_mm": hole_length + passage_overlap + diameter * max(
                [default_inner_overlap_D]
                + [float(value) for value in inner_overlap_by_surface_D.values()]
            ),
            "default_inner_overlap_D": default_inner_overlap_D,
            "inner_overlap_D_by_surface": inner_overlap_by_surface_D,
            "span_count_per_row": span_count,
            "span_pitch_mm": span_pitch,
            "span_phase_fraction": phase,
            "profile_reconstruction": reconstruction,
        },
        "rows": rows_out,
        "airfoil_xy_mm": profile.tolist(),
    }


def write_csv(path: Path, layout: dict) -> None:
    fields = ["hole_id", "row_id", "surface", "s_over_s0", "x_mm", "y_mm", "z_mm",
              "axis_x", "axis_y", "diameter_mm", "injection_angle_deg", "orientation"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in layout["rows"]:
            for marker in row["cylinder_markers"]:
                writer.writerow({
                    "hole_id": marker["id"], "row_id": row["row_id"], "surface": row["surface"],
                    "s_over_s0": f'{row["s_over_s0"]:.9f}',
                    "x_mm": f'{row["surface_xy_mm"][0]:.6f}', "y_mm": f'{row["surface_xy_mm"][1]:.6f}',
                    "z_mm": f'{marker["start_mm"][2]:.6f}',
                    "axis_x": f'{row["coolant_exit_axis_xy"][0]:.9f}',
                    "axis_y": f'{row["coolant_exit_axis_xy"][1]:.9f}',
                    "diameter_mm": f'{layout["geometry"]["diameter_mm"]:.6f}',
                    "injection_angle_deg": f'{row["injection_angle_deg"]:.6f}',
                    "orientation": row["orientation"],
                })


def write_plot(path: Path, layout: dict) -> None:
    profile = np.asarray(layout["airfoil_xy_mm"])
    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    ax.fill(profile[:, 0], profile[:, 1], facecolor="0.88", edgecolor="black", lw=1.1)
    colors = {"suction": "tab:blue", "pressure": "tab:red"}
    for row in layout["rows"]:
        marker = row["cylinder_markers"][0]
        start = marker["start_mm"][:2]
        end = marker["end_mm"][:2]
        color = colors[row["surface"]]
        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, lw=4, alpha=0.75)
        p = row["surface_xy_mm"]
        ax.plot(p[0], p[1], "o", color=color)
        ax.annotate(f'{row["row_id"]} {row["s_over_s0"]:.4f}', p, xytext=(5, 5), textcoords="offset points")
    ax.set_aspect("equal")
    ax.set_xlim(12, 45)
    ax.set_ylim(78, 133)
    ax.grid(True, alpha=0.25)
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_title("Parametric downstream C3X film-hole layout")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", default=str(ROOT / "configs" / "c3x_downstream_design_baseline.json"))
    parser.add_argument("--out-json", default=str(ROOT / "configs" / "c3x_downstream_layout_resolved.json"))
    parser.add_argument("--out-csv", default=str(ROOT / "configs" / "c3x_downstream_layout_resolved.csv"))
    parser.add_argument("--out-png", default=str(ROOT / "configs" / "c3x_downstream_layout_resolved.png"))
    args = parser.parse_args()
    design = json.loads(Path(args.design).read_text(encoding="utf-8"))
    layout = build_layout(design)
    out_json, out_csv, out_png = map(lambda p: Path(p).resolve(), (args.out_json, args.out_csv, args.out_png))
    for path in (out_json, out_csv, out_png):
        path.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    write_csv(out_csv, layout)
    write_plot(out_png, layout)
    print("wrote:", out_json)
    print("wrote:", out_csv)
    print("wrote:", out_png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
