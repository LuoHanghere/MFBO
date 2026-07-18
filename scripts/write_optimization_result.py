"""Convert one CFD post directory into the optimizer's strict result contract."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_workbench_film_results import protected_eta_summary


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-dir", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-mass-imbalance", type=float, default=1.0e-4)
    parser.add_argument("--max-continuity-residual", type=float, default=5.0e-3)
    args = parser.parse_args()

    post = Path(args.post_dir).resolve()
    baseline = load_json(Path(args.baseline).resolve())
    bo = load_json(post / "bo_summary.json")
    mass = load_json(post / "mass_flow_summary.json")
    pressure = load_json(post / "pressure_summary.json")
    convergence = load_json(post / "convergence_summary.json")
    with (post / "eta_surface_faces.csv").open("r", encoding="utf-8") as stream:
        faces = list(csv.DictReader(stream))
    protected = protected_eta_summary(
        faces,
        float(bo["references"]["Tg_ref_K"]),
        float(bo["references"]["Tc_ref"]["value_K"]),
        pressure_xmin=float(baseline["protected_mask"]["pressure_xmin"]),
        suction_xmin=float(baseline["protected_mask"]["suction_xmin"]),
    )
    objective = float(protected["eta_bar"])
    coolant = float(mass["constraints"]["coolant_actual_kg_s"])
    loss_doc = pressure.get("pressure_loss_diagnostic") or {}
    loss = float(loss_doc["delta_total_pressure_Pa"])
    imbalance = abs(float(mass["constraints"]["mass_imbalance_kg_s"]))
    last = convergence.get("last_residual_row") or {}
    continuity = float(last.get("continuity", math.inf))
    warnings = convergence.get("warnings") or {}
    failures = []
    if not bo.get("valid"):
        failures.append("bo_summary.valid is false")
    if not math.isfinite(objective):
        failures.append("protected objective is not finite")
    if imbalance > args.max_mass_imbalance:
        failures.append(f"mass imbalance {imbalance:.6g} exceeds {args.max_mass_imbalance:.6g}")
    if continuity > args.max_continuity_residual:
        failures.append(
            f"continuity residual {continuity:.6g} exceeds {args.max_continuity_residual:.6g}"
        )
    if int(warnings.get("divergence", 0)) or int(warnings.get("floating_point", 0)):
        failures.append("solver log contains divergence or floating-point failure")
    if failures:
        raise RuntimeError("; ".join(failures))

    payload = {
        "objective": objective,
        "constraints": {
            "coolant_mass_ratio": coolant / float(baseline["coolant_actual_kg_s"]),
            "loss_ratio": loss / float(baseline["delta_total_pressure_Pa"]),
        },
        "metrics": {
            "whole_vane_eta_bar": bo["objective"]["eta_bar"],
            "protected_area_m2": protected["area_m2"],
            "coolant_actual_kg_s": coolant,
            "delta_total_pressure_Pa": loss,
            "mass_imbalance_kg_s": imbalance,
            "continuity_residual": continuity,
            "y_plus_p95": bo["constraints"].get("y_plus_p95"),
            "y_plus_max": bo["constraints"].get("y_plus_max"),
            "converged_for_screening": True,
        },
    }
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
