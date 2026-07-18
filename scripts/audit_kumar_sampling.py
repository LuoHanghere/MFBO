"""Audit Kumar Fig. 6/7 wall sampling positions and outlier influence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator


ROOT = Path(__file__).resolve().parents[1]


def metrics(predicted: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    error = predicted - reference
    return {
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mae": float(np.mean(np.abs(error))),
        "mean_bias": float(np.mean(error)),
        "mean_cfd": float(np.mean(predicted)),
        "mean_reference": float(np.mean(reference)),
        "shape_correlation": float(np.corrcoef(predicted, reference)[0, 1]),
    }


def interpolate_side(faces: pd.DataFrame):
    points = faces[["X_over_Cax", "Z_over_D"]].to_numpy(float)
    values = faces["eta"].to_numpy(float)
    return LinearNDInterpolator(points, values), NearestNDInterpolator(points, values)


def sample(interpolators, station: float, z: np.ndarray) -> np.ndarray:
    query = np.column_stack([np.full_like(z, station), z])
    linear = np.asarray(interpolators[0](query), dtype=float)
    nearest = np.asarray(interpolators[1](query), dtype=float)
    return np.where(np.isfinite(linear), linear, nearest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--faces", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--tg-K", type=float, default=1773.0)
    parser.add_argument("--tc-K", type=float, default=591.0)
    parser.add_argument(
        "--layout-json",
        default=str(ROOT / "configs/c3x_downstream_layout_resolved.json"),
    )
    args = parser.parse_args()

    faces = pd.read_csv(args.faces)
    layout = json.loads(Path(args.layout_json).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    definitions = {
        "pressure": {
            "published_station": 0.31,
            "reference": ROOT / "configs/validation/kumar_fig6_ps_forward_30deg.csv",
            "sweep": (0.05, 0.98),
        },
        "suction": {
            "published_station": 0.48,
            "reference": ROOT / "configs/validation/kumar_fig7_ss_forward_35deg.csv",
            "sweep": (0.05, 0.98),
        },
    }

    total_area = float(faces.face_area_m2.sum())
    physical = faces.Taw_K.between(args.tc_K, args.tg_K)
    result = {
        "sampling_definition": (
            "X/Cax is the axial location magnitude measured from the stagnation-point frame; "
            "pressure is reported with a negative sign and suction with a positive sign."
        ),
        "outlier_area_audit": {
            "total_wall_area_m2": total_area,
            "physical_temperature_area_fraction": float(faces.loc[physical, "face_area_m2"].sum() / total_area),
            "above_mainstream_face_count": int((faces.Taw_K > args.tg_K).sum()),
            "above_mainstream_area_fraction": float(faces.loc[faces.Taw_K > args.tg_K, "face_area_m2"].sum() / total_area),
            "below_coolant_face_count": int((faces.Taw_K < args.tc_K).sum()),
            "below_coolant_area_fraction": float(faces.loc[faces.Taw_K < args.tc_K, "face_area_m2"].sum() / total_area),
        },
        "sides": {},
    }

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5))
    for row_index, (side, spec) in enumerate(definitions.items()):
        side_faces = faces[faces.side == side].copy()
        ref = pd.read_csv(spec["reference"])
        z_min = float(side_faces.Z_over_D.min())
        z_max = float(side_faces.Z_over_D.max())
        ref = ref[(ref.Z_over_D >= z_min) & (ref.Z_over_D <= z_max)].copy()
        z = ref.Z_over_D.to_numpy(float)
        reference = ref.eta.to_numpy(float)
        interpolators = interpolate_side(side_faces)
        station = float(spec["published_station"])
        published = sample(interpolators, station, z)

        row_x_mm = [
            float(row["surface_xy_mm"][0])
            for row in layout["rows"]
            if row["surface"] == side
        ]
        last_row_station = max(row_x_mm) / 78.16
        relative_downstream_station = last_row_station + station

        sweep_low = max(float(spec["sweep"][0]), float(side_faces.X_over_Cax.min()))
        sweep_high = min(float(spec["sweep"][1]), float(side_faces.X_over_Cax.max()))
        sweep_x = np.linspace(sweep_low, sweep_high, 500)
        sweep_metrics = []
        for x in sweep_x:
            values = sample(interpolators, float(x), z)
            sweep_metrics.append(metrics(values, reference))
        rmse = np.array([item["rmse"] for item in sweep_metrics])
        correlation = np.array([item["shape_correlation"] for item in sweep_metrics])
        bias = np.array([item["mean_bias"] for item in sweep_metrics])
        best_index = int(np.argmin(rmse))
        correlation_index = int(np.nanargmax(correlation))
        bias_index = int(np.argmin(np.abs(bias)))
        candidate_stations = {
            "published_absolute": station,
            "published_distance_downstream_of_last_row": relative_downstream_station,
            "diagnostic_best_rmse": float(sweep_x[best_index]),
            "diagnostic_best_shape_correlation": float(sweep_x[correlation_index]),
            "diagnostic_best_absolute_mean_bias": float(sweep_x[bias_index]),
        }
        candidates = {}
        candidate_profiles = {}
        for name, candidate_station in candidate_stations.items():
            values = sample(interpolators, candidate_station, z)
            candidate_profiles[name] = values
            candidates[name] = {
                "station_X_over_Cax": candidate_station,
                "downstream_of_last_row": bool(candidate_station >= last_row_station),
                "metrics": metrics(values, reference),
            }
        station_band = side_faces[(side_faces.X_over_Cax - station).abs() <= 0.01]
        result["sides"][side] = {
            "published_station_X_over_Cax": station,
            "signed_station_X_over_Cax": -station if side == "pressure" else station,
            "published_station_metrics": metrics(published, reference),
            "diagnostic_best_station_X_over_Cax": float(sweep_x[best_index]),
            "diagnostic_best_station_metrics": sweep_metrics[best_index],
            "station_sweep_note": "Best station is diagnostic only and must not replace the published coordinate.",
            "last_downstream_row_X_over_Cax": last_row_station,
            "candidates": candidates,
            "station_band_half_width_X_over_Cax": 0.01,
            "station_band_face_count": int(len(station_band)),
            "station_band_temperature_min_K": float(station_band.Taw_K.min()),
            "station_band_temperature_max_K": float(station_band.Taw_K.max()),
        }

        ax = axes[row_index, 0]
        ax.plot(z, reference, "ko-", ms=3, lw=1.2, label="Kumar digitization")
        styles = {
            "published_absolute": ("r.-", "absolute X/Cax"),
            "published_distance_downstream_of_last_row": ("b.--", "distance after last row"),
            "diagnostic_best_rmse": ("g-.", "best RMSE"),
            "diagnostic_best_shape_correlation": ("m:", "best correlation"),
        }
        for name, (style, label) in styles.items():
            ax.plot(z, candidate_profiles[name], style, ms=3, lw=1, label=label)
        ax.set(title=f"{side}: coordinate hypotheses", ylabel="eta", ylim=(0, 1))
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)

        ax = axes[row_index, 1]
        ax.plot(sweep_x, rmse, "b-", label="RMSE")
        correlation_axis = ax.twinx()
        correlation_axis.plot(sweep_x, correlation, color="0.45", lw=1, label="correlation")
        ax.axvline(station, color="r", ls="--", label="published station")
        ax.axvline(last_row_station, color="0.5", ls="-.", label="last hole row")
        ax.axvline(relative_downstream_station, color="b", ls=":", label="distance-after-row")
        ax.axvline(sweep_x[best_index], color="k", ls=":", label="diagnostic minimum")
        ax.set(title=f"{side}: station sensitivity", ylabel="RMSE")
        correlation_axis.set_ylabel("shape correlation", color="0.4")
        correlation_axis.set_ylim(-1, 1)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7, loc="best")

    axes[-1, 0].set_xlabel("Z/D")
    axes[-1, 1].set_xlabel("X/Cax magnitude")
    fig.tight_layout()
    plot_path = out_dir / "kumar_sampling_audit.png"
    json_path = out_dir / "kumar_sampling_audit.json"
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(plot_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
