"""Create frozen-layout and unwrapped cooling-effectiveness figures for one trial."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator


def load_faces(path: Path) -> dict[str, np.ndarray]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                rows.append(
                    (
                        row["side"],
                        float(row["surface_distance_pct"]),
                        float(row["z_m"]),
                        float(row["Z_over_D"]),
                        float(row["Taw_K"]),
                        float(row["eta"]),
                        float(row["face_area_m2"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return {
        "side": np.asarray([row[0] for row in rows], dtype=object),
        "s_pct": np.asarray([row[1] for row in rows], dtype=float),
        "z_m": np.asarray([row[2] for row in rows], dtype=float),
        "z_d": np.asarray([row[3] for row in rows], dtype=float),
        "taw_k": np.asarray([row[4] for row in rows], dtype=float),
        "eta": np.asarray([row[5] for row in rows], dtype=float),
        "area": np.asarray([row[6] for row in rows], dtype=float),
    }


def interpolate_field(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    x_centers: np.ndarray,
    y_centers: np.ndarray,
) -> np.ndarray:
    """Project scattered face-center values without exposing empty histogram bins."""
    finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    points = np.column_stack((x[finite], y[finite]))
    field = values[finite]
    if len(field) < 3:
        raise RuntimeError("surface projection requires at least three finite faces")
    query_x, query_y = np.meshgrid(x_centers, y_centers)
    linear = LinearNDInterpolator(points, field, fill_value=np.nan, rescale=True)
    projected = np.asarray(linear(query_x, query_y), dtype=float)
    missing = ~np.isfinite(projected)
    if np.any(missing):
        nearest = NearestNDInterpolator(points, field, rescale=True)
        projected[missing] = nearest(query_x[missing], query_y[missing])
    return projected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", required=True)
    parser.add_argument("--post-dir", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--trial-label", default="optimization trial")
    parser.add_argument("--periodic-span-mm", type=float, default=14.85)
    args = parser.parse_args()

    layout = Path(args.layout).resolve()
    post_dir = Path(args.post_dir).resolve()
    result_path = Path(args.result).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    layout_copy = out_dir / "film_hole_layout.png"
    shutil.copy2(layout, layout_copy)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    faces = load_faces(post_dir / "eta_surface_faces.csv")
    finite = (
        np.isfinite(faces["s_pct"])
        & np.isfinite(faces["z_m"])
        & np.isfinite(faces["eta"])
        & np.isfinite(faces["area"])
        & (faces["area"] > 0.0)
    )
    if not np.any(finite):
        raise RuntimeError("eta_surface_faces.csv contains no finite plottable rows")

    z_span = faces["z_m"] / (args.periodic_span_mm * 1e-3) - 0.5
    x_edges = np.linspace(0.0, 100.0, 101)
    y_edges = np.linspace(-0.5, 0.5, 61)
    x_centers = 0.5 * (x_edges[:-1] + x_edges[1:])
    y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])
    fig, axes = plt.subplots(2, 1, figsize=(11.0, 6.8), sharex=True, constrained_layout=True)
    cmap = plt.get_cmap("turbo").copy()
    cmap.set_bad("#eeeeee")
    image = None
    for axis, side, label in zip(
        axes,
        ("pressure", "suction"),
        ("Pressure surface", "Suction surface"),
    ):
        selected = finite & (faces["side"] == side)
        grid = interpolate_field(
            faces["s_pct"][selected],
            z_span[selected],
            np.clip(faces["eta"][selected], 0.0, 1.0),
            x_centers,
            y_centers,
        )
        image = axis.pcolormesh(
            x_edges,
            y_edges,
            grid,
            cmap=cmap,
            vmin=0.0,
            vmax=1.0,
            shading="flat",
        )
        axis.set_ylabel("z / periodic span")
        axis.set_title(label, loc="left", fontsize=11)
        axis.grid(False)
    axes[-1].set_xlabel("Surface distance [%]")
    colorbar = fig.colorbar(image, ax=axes, pad=0.02, aspect=28)
    colorbar.set_label("Adiabatic film-cooling effectiveness, eta")
    objective = float(result["objective"])
    fidelity = result.get("metrics", {}).get("mesh_tier", "")
    fig.suptitle(
        f"{args.trial_label} | protected eta = {objective:.5f}"
        + (f" | {fidelity}" if fidelity else ""),
        fontsize=13,
    )
    map_path = out_dir / "cooling_efficiency_map.png"
    fig.savefig(map_path, dpi=180)
    plt.close(fig)

    layout_image = plt.imread(layout_copy)
    eta_image = plt.imread(map_path)
    overview, axes = plt.subplots(
        1, 2, figsize=(15.0, 7.0), gridspec_kw={"width_ratios": [0.72, 1.55]}
    )
    axes[0].imshow(layout_image)
    axes[0].axis("off")
    axes[0].set_title("Film-hole layout")
    axes[1].imshow(eta_image)
    axes[1].axis("off")
    axes[1].set_title("Surface cooling effectiveness")
    overview.suptitle(args.trial_label, fontsize=14)
    overview.tight_layout()
    overview.savefig(out_dir / "iteration_overview.png", dpi=160)
    plt.close(overview)

    manifest = {
        "trial_label": args.trial_label,
        "objective": objective,
        "eta_color_limits": [0.0, 1.0],
        "layout": str(layout_copy),
        "cooling_efficiency_map": str(map_path),
        "overview": str(out_dir / "iteration_overview.png"),
        "source_faces": str(post_dir / "eta_surface_faces.csv"),
    }
    (out_dir / "visual_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
