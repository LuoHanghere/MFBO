"""Plot coupled SS1/SS2 and PS1/PS2 fixed-plenum feasibility maps."""
from __future__ import annotations

import argparse
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
from scripts.validate_workbench_layout import (
    _load_cavities,
    _polygon_boundary_distance_xy,
)


ROOT = Path(__file__).resolve().parents[1]


def _signed_boundary_distance(point: np.ndarray, polygon: np.ndarray) -> float:
    distance = _polygon_boundary_distance_xy(point, polygon)
    return distance if point_in_poly_xy(point, polygon) else -distance


def _pair_margin(
    surface,
    profile: np.ndarray,
    polygon: np.ndarray,
    s1: float,
    s2: float,
    *,
    angle_deg: float,
    orientation: str,
    hole_length_mm: float,
    inner_overlap_mm: float,
    diameter_mm: float,
    additional_margin_d: float,
) -> float:
    """Return minimum cylinder-to-plenum clearance reserve [mm]."""
    center_s = 0.5 * (s1 + s2) * surface.reference_arc_mm
    center_point, tangent = surface.locate_reference_arc(center_s)
    normal = outward_normal(center_point, tangent, profile)
    alpha = math.radians(angle_deg)
    stream_sign = 1.0 if orientation == "forward" else -1.0
    exit_axis = stream_sign * math.cos(alpha) * tangent + math.sin(alpha) * normal
    exit_axis /= np.linalg.norm(exit_axis)
    into_axis = -exit_axis

    required = 0.5 * diameter_mm + additional_margin_d * diameter_mm
    reserves = []
    for fraction in (s1, s2):
        point, _ = surface.locate_reference_arc(fraction * surface.reference_arc_mm)
        outside_ok = not point_in_poly_xy(point + 0.2 * diameter_mm * exit_axis, profile)
        inside_ok = point_in_poly_xy(point + 0.2 * diameter_mm * into_axis, profile)
        if not (outside_ok and inside_ok):
            return -required
        endpoint = point + (hole_length_mm + inner_overlap_mm) * into_axis
        reserves.append(_signed_boundary_distance(endpoint, polygon) - required)
    return float(min(reserves))


def _scan_pair(
    design: dict,
    cavities: dict[str, np.ndarray],
    surface_name: str,
    row_ids: tuple[str, str],
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    resolution: int,
    margin_d: float,
) -> dict:
    surfaces, profile, _ = build_paper_surfaces()
    surface = surfaces[surface_name]
    cavity_name = "SS_plenum" if surface_name == "suction" else "PS_plenum"
    polygon = cavities[cavity_name]
    geometry = design["geometry"]
    settings = design["surface_settings"][surface_name]
    diameter = float(geometry["diameter_mm"])
    x = np.linspace(xlim[0], xlim[1], resolution)
    y = np.linspace(ylim[0], ylim[1], resolution)
    values = np.empty((resolution, resolution), dtype=float)
    for iy, s2 in enumerate(y):
        for ix, s1 in enumerate(x):
            if s2 <= s1:
                values[iy, ix] = np.nan
                continue
            values[iy, ix] = _pair_margin(
                surface,
                profile,
                polygon,
                float(s1),
                float(s2),
                angle_deg=float(settings["injection_angle_deg"]),
                orientation=str(settings["orientation"]),
                hole_length_mm=float(geometry["physical_hole_length_mm"]),
                inner_overlap_mm=float(geometry["inner_overlap_D"]) * diameter,
                diameter_mm=diameter,
                additional_margin_d=margin_d,
            )
    baseline = (
        float(design["rows"][row_ids[0]]["s_over_s0"]),
        float(design["rows"][row_ids[1]]["s_over_s0"]),
    )
    baseline_margin = _pair_margin(
        surface,
        profile,
        polygon,
        baseline[0],
        baseline[1],
        angle_deg=float(settings["injection_angle_deg"]),
        orientation=str(settings["orientation"]),
        hole_length_mm=float(geometry["physical_hole_length_mm"]),
        inner_overlap_mm=float(geometry["inner_overlap_D"]) * diameter,
        diameter_mm=diameter,
        additional_margin_d=margin_d,
    )
    feasible = np.isfinite(values) & (values >= 0.0)
    return {
        "surface": surface_name,
        "row_ids": row_ids,
        "x": x,
        "y": y,
        "values": values,
        "baseline": baseline,
        "baseline_margin_mm": baseline_margin,
        "feasible_fraction": float(feasible.sum() / np.isfinite(values).sum()),
        "feasible_x_extent": [float(x[np.where(feasible)[1]].min()), float(x[np.where(feasible)[1]].max())],
        "feasible_y_extent": [float(y[np.where(feasible)[0]].min()), float(y[np.where(feasible)[0]].max())],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--design",
        default=str(ROOT / "configs" / "c3x_downstream_design_baseline.json"),
    )
    parser.add_argument(
        "--cavities",
        default=str(ROOT / "configs" / "c3x_fixed_downstream_plenums.json"),
    )
    parser.add_argument(
        "--conditional-ranges",
        default=str(ROOT / "configs" / "c3x_row_feasible_ranges_baseline_angles.json"),
    )
    parser.add_argument("--resolution", type=int, default=101)
    parser.add_argument("--margin-d", type=float, default=0.25)
    parser.add_argument(
        "--out-png",
        default=str(ROOT / "configs" / "c3x_pair_feasibility_map.png"),
    )
    parser.add_argument(
        "--out-json",
        default=str(ROOT / "configs" / "c3x_pair_feasibility_map.json"),
    )
    args = parser.parse_args()

    design_path = Path(args.design).resolve()
    cavity_path = Path(args.cavities).resolve()
    design = json.loads(design_path.read_text(encoding="utf-8"))
    cavities = _load_cavities(cavity_path)
    conditional = json.loads(Path(args.conditional_ranges).read_text(encoding="utf-8"))

    scans = [
        _scan_pair(
            design,
            cavities,
            "suction",
            ("SS1", "SS2"),
            (0.20, 0.30),
            (0.21, 0.33),
            args.resolution,
            args.margin_d,
        ),
        _scan_pair(
            design,
            cavities,
            "pressure",
            ("PS1", "PS2"),
            (0.16, 0.28),
            (0.17, 0.32),
            args.resolution,
            args.margin_d,
        ),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.4), constrained_layout=True)
    levels = [-5.0, -2.0, -1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0, 2.0, 5.0]
    contour = None
    for ax, scan in zip(axes, scans):
        x, y, values = scan["x"], scan["y"], scan["values"]
        xx, yy = np.meshgrid(x, y)
        contour = ax.contourf(xx, yy, values, levels=levels, cmap="RdYlGn", extend="both")
        ax.contour(xx, yy, values, levels=[0.0], colors="black", linewidths=2.2)
        invalid_order = yy <= xx
        ax.contourf(xx, yy, invalid_order.astype(float), levels=[0.5, 1.5], colors=["0.72"], alpha=0.85)
        narrow_gap = (yy > xx) & ((yy - xx) < 0.005)
        ax.contourf(
            xx,
            yy,
            narrow_gap.astype(float),
            levels=[0.5, 1.5],
            colors="none",
            hatches=["////"],
        )
        row1, row2 = scan["row_ids"]
        bx, by = scan["baseline"]
        ax.plot(bx, by, marker="*", ms=15, color="#1454d8", mec="white", mew=1.0, label="Baseline")
        for value in conditional["rows"][row1]["baseline_interval"]:
            ax.axvline(value, color="#1454d8", ls="--", lw=1.0, alpha=0.75)
        for value in conditional["rows"][row2]["baseline_interval"]:
            ax.axhline(value, color="#1454d8", ls="--", lw=1.0, alpha=0.75)
        ax.set_xlabel(f"{row1}  s/s0")
        ax.set_ylabel(f"{row2}  s/s0")
        angle = design["surface_settings"][scan["surface"]]["injection_angle_deg"]
        ax.set_title(
            f"{scan['surface'].title()} pair ({angle:g} deg)\n"
            f"baseline reserve = {scan['baseline_margin_mm']:.3f} mm"
        )
        ax.grid(alpha=0.18)
        ax.legend(loc="upper left")
    assert contour is not None
    cbar = fig.colorbar(contour, ax=axes, shrink=0.94, pad=0.02)
    cbar.set_label("Minimum plenum-clearance reserve [mm]  (>= 0 feasible)")
    fig.suptitle(
        f"C3X coupled row-position feasibility; fixed plenums; radius + {args.margin_d:.2f}D margin\n"
        "Black: feasibility boundary | Gray: reversed row order | Hatched: row gap < 0.005",
        fontsize=12,
    )
    out_png = Path(args.out_png).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220, bbox_inches="tight")
    plt.close(fig)

    report = {
        "status": "ok",
        "design": str(design_path),
        "cavities": str(cavity_path),
        "additional_margin_D": args.margin_d,
        "resolution": args.resolution,
        "plot": str(out_png),
        "pairs": [
            {
                key: scan[key]
                for key in (
                    "surface",
                    "row_ids",
                    "baseline",
                    "baseline_margin_mm",
                    "feasible_fraction",
                    "feasible_x_extent",
                    "feasible_y_extent",
                )
            }
            for scan in scans
        ],
        "interpretation": {
            "black_contour": "dynamic geometry-gate boundary (reserve = 0 mm)",
            "green": "full hole radius plus requested margin fits inside the assigned plenum",
            "red": "cavity miss or insufficient cylinder clearance",
            "gray": "row order is reversed",
            "hatched": "ordered but row separation is below 0.005 s/s0",
            "blue_dashed": "one-row-at-a-time conditional intervals from the earlier scan",
        },
    }
    out_json = Path(args.out_json).resolve()
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
