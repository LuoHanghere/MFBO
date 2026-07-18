"""Compute paired FC/NFC Stanton-number reduction and compare with NASA.

The FC and NFC calculations must use the same mesh, mainstream state, and
prescribed wall temperature. Under those conditions the common Stanton
normalization cancels, so SNR can be computed robustly from wall heat flux:

    SNR = 1 - q_FC / q_NFC
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree


DEFAULT_FACE_FILE = "heat_transfer_heat_flux_surface_faces.csv"


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def numeric(row: dict[str, Any], key: str) -> float:
    return float(row[key])


def pair_face_rows(
    fc_rows: list[dict[str, Any]],
    nfc_rows: list[dict[str, Any]],
    value_key: str,
    tolerance_m: float,
) -> list[dict[str, Any]]:
    paired: list[dict[str, Any]] = []
    for side in ("pressure", "suction"):
        fc_side = [row for row in fc_rows if row.get("side") == side]
        nfc_side = [row for row in nfc_rows if row.get("side") == side]
        if not fc_side or not nfc_side:
            continue
        nfc_xyz = np.asarray([
            [numeric(row, "x_m"), numeric(row, "y_m"), numeric(row, "z_m")]
            for row in nfc_side
        ])
        tree = cKDTree(nfc_xyz)
        fc_xyz = np.asarray([
            [numeric(row, "x_m"), numeric(row, "y_m"), numeric(row, "z_m")]
            for row in fc_side
        ])
        distances, indices = tree.query(fc_xyz, k=1)
        for fc, distance, index in zip(fc_side, distances, indices):
            if not math.isfinite(float(distance)) or float(distance) > tolerance_m:
                continue
            nfc = nfc_side[int(index)]
            q_fc = numeric(fc, value_key)
            q_nfc = numeric(nfc, value_key)
            if not math.isfinite(q_fc) or not math.isfinite(q_nfc) or abs(q_nfc) < 1e-12:
                continue
            paired.append({
                "side": side,
                "surface_distance_pct": numeric(fc, "surface_distance_pct"),
                "x_m": numeric(fc, "x_m"),
                "y_m": numeric(fc, "y_m"),
                "z_m": numeric(fc, "z_m"),
                "face_area_m2": numeric(fc, "face_area_m2"),
                "q_fc_W_m2": q_fc,
                "q_nfc_W_m2": q_nfc,
                "snr": 1.0 - q_fc / q_nfc,
                "pair_distance_m": float(distance),
            })
    return paired


def binned_rows(rows: list[dict[str, Any]], bin_width_pct: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for side in ("pressure", "suction"):
        subset = [row for row in rows if row["side"] == side]
        bins: dict[int, list[dict[str, Any]]] = {}
        for row in subset:
            index = int(math.floor(float(row["surface_distance_pct"]) / bin_width_pct))
            bins.setdefault(index, []).append(row)
        for index, values in sorted(bins.items()):
            weights = np.asarray([float(row["face_area_m2"]) for row in values])
            snr = np.asarray([float(row["snr"]) for row in values])
            q_fc = np.asarray([float(row["q_fc_W_m2"]) for row in values])
            q_nfc = np.asarray([float(row["q_nfc_W_m2"]) for row in values])
            finite = (
                np.isfinite(weights) & np.isfinite(snr)
                & np.isfinite(q_fc) & np.isfinite(q_nfc) & (weights > 0.0)
            )
            if not finite.any():
                continue
            weights = weights[finite]
            snr = snr[finite]
            q_fc = q_fc[finite]
            q_nfc = q_nfc[finite]
            q_fc_mean = float(np.average(q_fc, weights=weights))
            q_nfc_mean = float(np.average(q_nfc, weights=weights))
            if abs(q_nfc_mean) < 1e-12:
                continue
            snr_mean = 1.0 - q_fc_mean / q_nfc_mean
            out.append({
                "side": side,
                "surface_distance_pct": (index + 0.5) * bin_width_pct,
                "snr": snr_mean,
                "q_fc_area_mean_W_m2": q_fc_mean,
                "q_nfc_area_mean_W_m2": q_nfc_mean,
                "pointwise_snr_std": float(np.sqrt(np.average((snr - np.average(snr, weights=weights)) ** 2, weights=weights))),
                "face_count": int(finite.sum()),
                "area_m2": float(weights.sum()),
            })
    return out


def compare_experiment(
    simulation: list[dict[str, Any]], experiment: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    compared: list[dict[str, Any]] = []
    side_metrics: dict[str, Any] = {}
    for side in ("pressure", "suction"):
        sim = sorted(
            (row for row in simulation if row["side"] == side),
            key=lambda row: float(row["surface_distance_pct"]),
        )
        exp = [row for row in experiment if row.get("side") == side]
        if len(sim) < 2 or not exp:
            continue
        sx = np.asarray([float(row["surface_distance_pct"]) for row in sim])
        sy = np.asarray([float(row["snr"]) for row in sim])
        side_errors = []
        for row in exp:
            x = float(row["surface_distance_pct"])
            if x < sx.min() or x > sx.max():
                continue
            predicted = float(np.interp(x, sx, sy))
            observed = float(row["snr"])
            error = predicted - observed
            side_errors.append(error)
            compared.append({
                "side": side,
                "surface_distance_pct": x,
                "nasa_snr": observed,
                "cfd_snr": predicted,
                "error": error,
            })
        if side_errors:
            arr = np.asarray(side_errors)
            side_metrics[side] = {
                "point_count": int(arr.size),
                "mae": float(np.mean(np.abs(arr))),
                "rmse": float(np.sqrt(np.mean(arr ** 2))),
                "bias": float(np.mean(arr)),
            }
    errors = np.asarray([float(row["error"]) for row in compared])
    summary = {
        "definition": "SNR = 1 - q_FC/q_NFC on identical prescribed-Tw meshes",
        "point_count": int(errors.size),
        "mae": None if not errors.size else float(np.mean(np.abs(errors))),
        "rmse": None if not errors.size else float(np.sqrt(np.mean(errors ** 2))),
        "bias": None if not errors.size else float(np.mean(errors)),
        "sides": side_metrics,
        "reference_quality": "NASA Figure 30 approximate manual digitization; trend-validation use only",
    }
    return compared, summary


def plot_comparison(
    simulation: list[dict[str, Any]],
    experiment: list[dict[str, Any]],
    output: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, side, title in zip(axes, ("pressure", "suction"), ("Pressure side", "Suction side")):
        sim = sorted(
            (row for row in simulation if row["side"] == side),
            key=lambda row: float(row["surface_distance_pct"]),
        )
        exp = sorted(
            (row for row in experiment if row.get("side") == side),
            key=lambda row: float(row["surface_distance_pct"]),
        )
        if sim:
            ax.plot(
                [float(row["surface_distance_pct"]) for row in sim],
                [float(row["snr"]) for row in sim],
                color="#167d86", linewidth=1.8, label="CFD paired SNR",
            )
        if exp:
            ax.scatter(
                [float(row["surface_distance_pct"]) for row in exp],
                [float(row["snr"]) for row in exp],
                facecolors="none", edgecolors="#c63d2f", marker="D", s=28,
                label="NASA 44344 Fig. 30",
            )
        ax.axhline(0.0, color="#777777", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel("Surface distance (%)")
        ax.grid(True, alpha=0.22)
        ax.set_xlim(25, 100)
        ax.set_ylim(-0.65, 0.70)
    axes[0].set_ylabel("Stanton number reduction, SNR")
    axes[1].legend(frameon=False, loc="best")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--fc-post", required=True)
    parser.add_argument("--nfc-post", required=True)
    parser.add_argument("--face-file", default=DEFAULT_FACE_FILE)
    parser.add_argument("--value-key", default="heat_flux")
    parser.add_argument("--pair-tolerance-m", type=float, default=1e-9)
    parser.add_argument("--bin-width-pct", type=float, default=2.0)
    parser.add_argument(
        "--nasa-reference",
        default=str(root / "configs" / "validation" / "nasa_cr182133_fig30_run44344_snr.csv"),
    )
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    fc_path = Path(args.fc_post).resolve() / args.face_file
    nfc_path = Path(args.nfc_post).resolve() / args.face_file
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    paired = pair_face_rows(
        read_rows(fc_path), read_rows(nfc_path), args.value_key, args.pair_tolerance_m
    )
    if not paired:
        raise SystemExit("No FC/NFC wall faces could be paired")
    binned = binned_rows(paired, args.bin_width_pct)
    experiment = read_rows(Path(args.nasa_reference).resolve())
    compared, summary = compare_experiment(binned, experiment)
    summary.update({
        "fc_face_file": str(fc_path),
        "nfc_face_file": str(nfc_path),
        "paired_face_count": len(paired),
        "binned_point_count": len(binned),
        "pair_distance_max_m": max(float(row["pair_distance_m"]) for row in paired),
        "bin_width_pct": args.bin_width_pct,
    })

    write_rows(out_dir / "snr_surface_faces.csv", paired)
    write_rows(out_dir / "snr_surface_binned.csv", binned)
    write_rows(out_dir / "snr_nasa_comparison.csv", compared)
    (out_dir / "snr_validation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    plot_comparison(binned, experiment, out_dir / "snr_nasa_comparison.png")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
