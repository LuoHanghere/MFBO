"""Validate and plot three translated C3X pitch-periodic cells."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _point_polyline_dist(points: np.ndarray, polyline: np.ndarray) -> float:
    seg_a = polyline[:-1]
    seg = polyline[1:] - seg_a
    seg2 = np.einsum("ij,ij->i", seg, seg) + 1.0e-30
    best = np.inf
    for point in points:
        rel = point - seg_a
        t = np.clip(np.einsum("ij,ij->i", rel, seg) / seg2, 0.0, 1.0)
        projection = seg_a + t[:, None] * seg
        best = min(best, float(np.min(np.linalg.norm(point - projection, axis=1))))
    return best


def _polygon_distance(a: np.ndarray, b: np.ndarray) -> float:
    if np.any(MplPath(a).contains_points(b[:-1])) or np.any(MplPath(b).contains_points(a[:-1])):
        return 0.0
    b0 = b[:-1]
    b1 = b[1:]
    for a0, a1 in zip(a[:-1], a[1:]):
        va = a1 - a0
        vb = b1 - b0
        cross_a_b0 = va[0] * (b0[:, 1] - a0[1]) - va[1] * (b0[:, 0] - a0[0])
        cross_a_b1 = va[0] * (b1[:, 1] - a0[1]) - va[1] * (b1[:, 0] - a0[0])
        cross_b_a0 = vb[:, 0] * (a0[1] - b0[:, 1]) - vb[:, 1] * (a0[0] - b0[:, 0])
        cross_b_a1 = vb[:, 0] * (a1[1] - b0[:, 1]) - vb[:, 1] * (a1[0] - b0[:, 0])
        if np.any((cross_a_b0 * cross_a_b1 <= 0.0) & (cross_b_a0 * cross_b_a1 <= 0.0)):
            return 0.0
    return min(_point_polyline_dist(a[:-1], b), _point_polyline_dist(b[:-1], a))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--geometry",
        default=str(ROOT / "configs" / "c3x_kumar_paper_external_flow.json"),
    )
    parser.add_argument(
        "--out-prefix",
        default=str(
            ROOT / "runs" / "workbench" / "periodic_v2" / "geometry_freeze"
            / "c3x_periodic_three_cell"
        ),
    )
    args = parser.parse_args()

    geometry_path = Path(args.geometry).resolve()
    prefix = Path(args.out_prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(geometry_path.read_text(encoding="utf-8"))

    translation = np.asarray(data["periodic_translation_xy_mm"], dtype=float)
    pitch = float(data["physical_pitch_mm"])
    lower = np.asarray(data["periodic_lower_xy_mm"], dtype=float)
    upper = np.asarray(data["periodic_upper_xy_mm"], dtype=float)
    airfoil = np.asarray(data["airfoil_xy_mm"], dtype=float)
    outer = np.asarray(data["outer_loop_xy_mm"], dtype=float)
    inlet = np.asarray(data["inlet_xy_mm"], dtype=float)
    outlet = np.asarray(data["outlet_xy_mm"], dtype=float)

    pair_count = min(len(lower), len(upper))
    pair_error = float(np.max(np.linalg.norm(upper[:pair_count] - translation - lower[:pair_count], axis=1)))
    inlet_dx = float(abs(inlet[1, 0] - inlet[0, 0]))
    outlet_dx = float(abs(outlet[1, 0] - outlet[0, 0]))
    lower_neighbor_gap = _polygon_distance(airfoil, airfoil - translation)
    upper_neighbor_gap = _polygon_distance(airfoil, airfoil + translation)
    neighbor_gap = min(lower_neighbor_gap, upper_neighbor_gap)

    checks = {
        "translation_is_physical_pitch_y": bool(
            abs(translation[0]) <= 1.0e-10 and abs(translation[1] - pitch) <= 1.0e-10
        ),
        "inlet_parallel_to_y": inlet_dx <= 1.0e-10,
        "outlet_parallel_to_y": outlet_dx <= 1.0e-10,
        "periodic_walls_match": pair_error <= 1.0e-9,
        "adjacent_blades_have_positive_gap": neighbor_gap > 0.0,
    }
    report = {
        "status": "ok" if all(checks.values()) else "failed",
        "geometry_json": str(geometry_path),
        "units": "mm",
        "physical_pitch_mm": pitch,
        "periodic_translation_xy_mm": translation.tolist(),
        "inlet_endpoint_dx_mm": inlet_dx,
        "outlet_endpoint_dx_mm": outlet_dx,
        "periodic_pair_max_mismatch_mm": pair_error,
        "adjacent_blade_gap_mm": neighbor_gap,
        "adjacent_blade_gap_lower_mm": lower_neighbor_gap,
        "adjacent_blade_gap_upper_mm": upper_neighbor_gap,
        "blade_to_periodic_wall_min_gap_mm": float(data["min_wall_clearance_mm"]),
        "checks": checks,
    }
    snapshot_path = prefix.with_name(prefix.name + "_geometry.json")
    snapshot_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    report["frozen_geometry_json"] = str(snapshot_path)
    report_path = prefix.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(8.5, 12))
    colors = ["#e8eef2", "#d9f0f1", "#e8eef2"]
    for index, offset_factor in enumerate((-1, 0, 1)):
        offset = offset_factor * translation
        shifted_outer = outer + offset
        shifted_airfoil = airfoil + offset
        ax.fill(
            shifted_outer[:, 0], shifted_outer[:, 1],
            facecolor=colors[index], edgecolor="#54717c", linewidth=0.8,
            alpha=0.72, label="periodic cells" if offset_factor == 0 else None,
        )
        ax.fill(
            shifted_airfoil[:, 0], shifted_airfoil[:, 1],
            facecolor="#b8b8b8", edgecolor="#161616", linewidth=1.2,
            zorder=4, label="C3X vanes" if offset_factor == 0 else None,
        )
        ax.text(
            float(np.min(shifted_outer[:, 0])) + 6.0,
            float(np.max(shifted_outer[:, 1])) - 12.0,
            f"cell {offset_factor:+d}", fontsize=9, color="#33464d",
        )

    ax.plot(lower[:, 0], lower[:, 1], color="#d97904", linewidth=2.0, label="periodic low")
    ax.plot(upper[:, 0], upper[:, 1], "--", color="#7d53a6", linewidth=2.0, label="periodic high")
    ax.plot(inlet[:, 0], inlet[:, 1], color="#18864b", linewidth=3.0, label="inlet")
    ax.plot(outlet[:, 0], outlet[:, 1], color="#c93434", linewidth=3.0, label="outlet")
    ax.annotate(
        f"T = ({translation[0]:.2f}, {translation[1]:.2f}) mm",
        xy=tuple(airfoil[0] + translation), xytext=tuple(airfoil[0] + 0.35 * translation),
        arrowprops={"arrowstyle": "->", "color": "#24557a"}, color="#24557a",
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.22)
    ax.set_xlabel("x [mm] (axial)")
    ax.set_ylabel("y [mm] (tangential)")
    ax.set_title("C3X three-cell pitch-periodic geometry check")
    ax.legend(loc="upper right", fontsize=8)
    fig.savefig(prefix.with_suffix(".png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(json.dumps(report, indent=2))
    print("plot:", prefix.with_suffix(".png"))
    print("report:", report_path)
    print("frozen geometry:", snapshot_path)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
