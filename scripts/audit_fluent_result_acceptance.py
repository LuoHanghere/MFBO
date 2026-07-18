"""Quantify whether localized numerical outliers can be ignored for each use."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

import h5py


def weighted_eta(rows: list[dict], *, clipped: bool) -> float:
    area = sum(float(row["face_area_m2"]) for row in rows)
    values = []
    for row in rows:
        eta = float(row["eta"])
        values.append(float(row["face_area_m2"]) * (max(0.0, min(1.0, eta)) if clipped else eta))
    return sum(values) / area


def wall_impact(rows: list[dict], tc: float, tg: float) -> dict:
    area = sum(float(row["face_area_m2"]) for row in rows)
    low = [row for row in rows if float(row["Taw_K"]) < tc]
    high = [row for row in rows if float(row["Taw_K"]) > tg]
    raw = weighted_eta(rows, clipped=False)
    clipped = weighted_eta(rows, clipped=True)
    return {
        "face_count": len(rows),
        "area_m2": area,
        "eta_raw": raw,
        "eta_clipped_0_1": clipped,
        "eta_absolute_change": abs(clipped - raw),
        "below_coolant_area_fraction": sum(float(r["face_area_m2"]) for r in low) / area,
        "above_mainstream_area_fraction": sum(float(r["face_area_m2"]) for r in high) / area,
        "outlier_area_fraction": sum(float(r["face_area_m2"]) for r in low + high) / area,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--post-dir", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--out")
    parser.add_argument("--max-hard-limit-fraction", type=float, default=2.0e-5)
    parser.add_argument("--max-wall-outlier-area-fraction", type=float, default=1.0e-3)
    parser.add_argument("--max-eta-change", type=float, default=1.0e-4)
    parser.add_argument("--max-mass-imbalance-fraction", type=float, default=5.0e-4)
    args = parser.parse_args()

    post = Path(args.post_dir).resolve()
    bo = json.loads((post / "bo_summary.json").read_text(encoding="utf-8"))
    with (post / "eta_surface_faces.csv").open("r", encoding="utf-8") as stream:
        faces = list(csv.DictReader(stream))
    tc = float(bo["references"]["Tc_ref"]["value_K"])
    tg = float(bo["references"]["Tg_ref_K"])
    protected = [
        row for row in faces
        if (row["side"] == "pressure" and float(row["X_over_Cax"]) >= 0.26530)
        or (row["side"] == "suction" and float(row["X_over_Cax"]) >= 0.37638)
    ]
    with h5py.File(Path(args.data).resolve(), "r") as data_file:
        temperature = data_file["results/1/phase-1/cells/SV_T/1"][:]
    hot = int((temperature >= 4999.0).sum())
    cold = int((temperature <= 1.001).sum())
    hard_fraction = (hot + cold) / len(temperature)
    log_text = Path(args.log).resolve().read_text(encoding="utf-8", errors="ignore")
    pressure_limit_messages = len(re.findall(r"absolute pressure limited", log_text, re.I))
    convergence = bo["diagnostics"]["convergence"]
    residual = convergence.get("last_residual_row") or {}
    outlet = abs(float(json.loads((post / "mass_flow_summary.json").read_text(encoding="utf-8"))["zones"]["outlet"]["mass_flow_kg_s"]))
    imbalance_fraction = abs(float(bo["constraints"]["mass_imbalance"])) / outlet
    whole_impact = wall_impact(faces, tc, tg)
    protected_impact = wall_impact(protected, tc, tg)

    alignment_path = post / "kumar_alignment_metrics.json"
    alignment = json.loads(alignment_path.read_text(encoding="utf-8")) if alignment_path.exists() else None
    side_checks = {}
    if alignment:
        for side, metrics in alignment["sides"].items():
            side_checks[side] = {
                "rmse": float(metrics["eta_rmse"]),
                "shape_correlation": float(metrics["shape_correlation"]),
                "pass": float(metrics["eta_rmse"]) <= 0.20
                and float(metrics["shape_correlation"]) >= 0.50,
            }
    eta_screening_usable = (
        hard_fraction <= args.max_hard_limit_fraction
        and protected_impact["outlier_area_fraction"] <= args.max_wall_outlier_area_fraction
        and protected_impact["eta_absolute_change"] <= args.max_eta_change
        and imbalance_fraction <= args.max_mass_imbalance_fraction
    )
    pressure_loss_usable = eta_screening_usable and pressure_limit_messages == 0 and hard_fraction == 0.0
    experiment_aligned = bool(side_checks) and all(item["pass"] for item in side_checks.values())
    payload = {
        "thresholds": {
            "max_hard_limit_fraction": args.max_hard_limit_fraction,
            "max_wall_outlier_area_fraction": args.max_wall_outlier_area_fraction,
            "max_eta_change": args.max_eta_change,
            "max_mass_imbalance_fraction": args.max_mass_imbalance_fraction,
            "kumar_rmse": 0.20,
            "kumar_shape_correlation": 0.50,
        },
        "cell_temperature": {
            "count": len(temperature),
            "min_K": float(temperature.min()),
            "max_K": float(temperature.max()),
            "hot_4999_count": hot,
            "cold_1_count": cold,
            "hard_limit_fraction": hard_fraction,
        },
        "wall_impact": {"whole": whole_impact, "protected": protected_impact},
        "mass_imbalance_fraction_of_outlet": imbalance_fraction,
        "pressure_limit_message_count": pressure_limit_messages,
        "last_residual": residual,
        "kumar_alignment": side_checks,
        "decisions": {
            "eta_screening_usable": eta_screening_usable,
            "pressure_loss_usable": pressure_loss_usable,
            "experiment_aligned": experiment_aligned,
            "paper_validation_usable": eta_screening_usable
            and pressure_loss_usable and experiment_aligned,
        },
        "interpretation": (
            "A result may be usable for wall eta while remaining unusable for pressure loss "
            "or experimental validation. Never transfer one acceptance decision to another metric."
        ),
    }
    out = Path(args.out).resolve() if args.out else post / "acceptance_summary.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
