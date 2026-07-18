"""Compare baseline and optimization wall-temperature/eta projections."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from plot_optimization_iteration import interpolate_field, load_faces


SIDES = (("pressure", "Pressure surface"), ("suction", "Suction surface"))


def project(
    faces: dict[str, np.ndarray],
    field: str,
    side: str,
    x_centers: np.ndarray,
    y_centers: np.ndarray,
    periodic_span_mm: float,
) -> np.ndarray:
    selected = (
        (faces["side"] == side)
        & np.isfinite(faces["s_pct"])
        & np.isfinite(faces["z_m"])
        & np.isfinite(faces[field])
        & np.isfinite(faces["area"])
        & (faces["area"] > 0.0)
    )
    z_span = faces["z_m"][selected] / (periodic_span_mm * 1e-3) - 0.5
    return interpolate_field(
        faces["s_pct"][selected],
        z_span,
        faces[field][selected],
        x_centers,
        y_centers,
    )


def make_comparison(
    baseline: dict[str, np.ndarray],
    optimized: dict[str, np.ndarray],
    field: str,
    baseline_label: str,
    optimized_label: str,
    objective_baseline: float,
    objective_optimized: float,
    periodic_span_mm: float,
    out: Path,
) -> dict:
    x_edges = np.linspace(0.0, 100.0, 201)
    y_edges = np.linspace(-0.5, 0.5, 101)
    x_centers = 0.5 * (x_edges[:-1] + x_edges[1:])
    y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])
    grids: dict[tuple[str, str], np.ndarray] = {}
    for side, _ in SIDES:
        grids[("baseline", side)] = project(
            baseline, field, side, x_centers, y_centers, periodic_span_mm
        )
        grids[("optimized", side)] = project(
            optimized, field, side, x_centers, y_centers, periodic_span_mm
        )
        grids[("delta", side)] = (
            grids[("optimized", side)] - grids[("baseline", side)]
        )

    paired = np.concatenate(
        [grids[(case, side)].ravel() for case in ("baseline", "optimized") for side, _ in SIDES]
    )
    if field == "taw_k":
        vmin, vmax = np.nanpercentile(paired, [1.0, 99.0])
        cmap = "inferno"
        value_label = "Adiabatic wall temperature, Taw [K]"
        delta_label = "Delta Taw = optimized - baseline [K]"
        title = "Adiabatic wall-temperature projection"
    else:
        vmin, vmax = 0.0, 1.0
        cmap = "turbo"
        value_label = "Adiabatic film-cooling effectiveness, eta"
        delta_label = "Delta eta = optimized - baseline"
        title = "Adiabatic film-cooling-effectiveness projection"
    deltas = np.concatenate([grids[("delta", side)].ravel() for side, _ in SIDES])
    delta_limit = max(float(np.nanpercentile(np.abs(deltas), 99.0)), 1e-6)

    fig, axes = plt.subplots(2, 3, figsize=(16.0, 7.2), sharex=True, sharey=True)
    value_image = None
    delta_image = None
    for row, (side, side_label) in enumerate(SIDES):
        for col, case in enumerate(("baseline", "optimized", "delta")):
            axis = axes[row, col]
            if case == "delta":
                delta_image = axis.pcolormesh(
                    x_edges,
                    y_edges,
                    grids[(case, side)],
                    cmap="RdBu_r",
                    vmin=-delta_limit,
                    vmax=delta_limit,
                    shading="flat",
                )
            else:
                value_image = axis.pcolormesh(
                    x_edges,
                    y_edges,
                    grids[(case, side)],
                    cmap=cmap,
                    vmin=vmin,
                    vmax=vmax,
                    shading="flat",
                )
            axis.set_title(side_label if col == 0 else "", loc="left", fontsize=10)
            axis.set_xlim(0.0, 100.0)
            axis.set_ylim(-0.5, 0.5)
            axis.grid(False)
        axes[row, 0].set_ylabel("z / periodic span")
    for axis in axes[-1, :]:
        axis.set_xlabel("Surface distance [%]")
    axes[0, 0].text(
        0.5, 1.12, f"{baseline_label}\nprotected eta = {objective_baseline:.5f}",
        transform=axes[0, 0].transAxes, ha="center", va="bottom", fontsize=11,
    )
    axes[0, 1].text(
        0.5, 1.12, f"{optimized_label}\nprotected eta = {objective_optimized:.5f}",
        transform=axes[0, 1].transAxes, ha="center", va="bottom", fontsize=11,
    )
    axes[0, 2].text(
        0.5, 1.12, "Difference\noptimized - baseline",
        transform=axes[0, 2].transAxes, ha="center", va="bottom", fontsize=11,
    )
    fig.subplots_adjust(left=0.06, right=0.90, bottom=0.10, top=0.82, wspace=0.08, hspace=0.14)
    value_bar = fig.colorbar(value_image, ax=axes[:, :2], pad=0.015, fraction=0.025)
    value_bar.set_label(value_label)
    delta_bar = fig.colorbar(delta_image, ax=axes[:, 2], pad=0.015, fraction=0.05)
    delta_bar.set_label(delta_label)
    fig.suptitle(title, fontsize=14, y=0.97)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return {
        "field": field,
        "output": str(out),
        "value_limits": [float(vmin), float(vmax)],
        "delta_limits": [-delta_limit, delta_limit],
        "coordinate": "surface_distance_pct versus z/periodic_span",
        "projection": "linear face-center interpolation with nearest boundary fill",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-faces", required=True)
    parser.add_argument("--optimized-faces", required=True)
    parser.add_argument("--baseline-objective", type=float, required=True)
    parser.add_argument("--optimized-objective", type=float, required=True)
    parser.add_argument("--baseline-label", default="Baseline")
    parser.add_argument("--optimized-label", default="Optimized")
    parser.add_argument("--periodic-span-mm", type=float, default=14.85)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline = load_faces(Path(args.baseline_faces).resolve())
    optimized = load_faces(Path(args.optimized_faces).resolve())
    records = []
    for field, filename in (
        ("taw_k", "temperature_projection_comparison.png"),
        ("eta", "cooling_effectiveness_projection_comparison.png"),
    ):
        records.append(
            make_comparison(
                baseline,
                optimized,
                field,
                args.baseline_label,
                args.optimized_label,
                args.baseline_objective,
                args.optimized_objective,
                args.periodic_span_mm,
                out_dir / filename,
            )
        )
    manifest = {
        "baseline_faces": str(Path(args.baseline_faces).resolve()),
        "optimized_faces": str(Path(args.optimized_faces).resolve()),
        "baseline_objective": args.baseline_objective,
        "optimized_objective": args.optimized_objective,
        "figures": records,
    }
    (out_dir / "projection_comparison_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
