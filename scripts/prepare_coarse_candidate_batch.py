"""Generate and geometry-check the reproducible initial coarse DoE batch."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.prior import FilmCoolingPrior
from bofm.optimization.surrogate import PhysicsInformedPolicy
from scripts.build_c3x_downstream_layout import build_layout
from scripts.validate_workbench_layout import _load_cavities, validate_layout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs/c3x_optimization_coarse.yaml"))
    parser.add_argument(
        "--base-design",
        default=str(ROOT / "configs/c3x_downstream_design_baseline.json"),
    )
    parser.add_argument("--baseline-objective", type=float, default=0.488920895845147)
    parser.add_argument("--out", default=str(ROOT / "runs/optimization/coarse/initial_candidates.json"))
    args = parser.parse_args()
    config = load_optimization_config(args.config)
    base = json.loads(
        Path(args.base_design).resolve().read_text(encoding="utf-8")
    )
    cavities = _load_cavities(ROOT / "configs/c3x_fixed_downstream_plenums.json")
    prior = FilmCoolingPrior(config.prior)
    policy = PhysicsInformedPolicy(config)
    # Seed every fidelity with the same baseline geometry so a multi-fidelity
    # policy does not return that geometry repeatedly as a missing calibration.
    trials = [
        {
            "id": index + 1,
            "design": config.baseline,
            "fidelity": fidelity.name,
            "status": "completed",
            "objective": args.baseline_objective,
            "constraints": {"coolant_mass_ratio": 1.0, "loss_ratio": 1.0},
            "relative_cost": fidelity.relative_cost,
        }
        for index, fidelity in enumerate(config.fidelities)
    ]
    candidates = []
    for index in range(1, config.initial_designs):
        proposal = policy.propose(trials)
        design = proposal.design
        geometry_design = json.loads(json.dumps(base))
        for row in ("SS1", "SS2", "PS1", "PS2"):
            geometry_design["rows"][row]["s_over_s0"] = float(design[f"{row}_s"])
        geometry_design["surface_settings"]["suction"]["injection_angle_deg"] = float(
            design["suction_angle_deg"]
        )
        geometry_design["surface_settings"]["pressure"]["injection_angle_deg"] = float(
            design["pressure_angle_deg"]
        )
        layout = build_layout(geometry_design)
        gate = validate_layout(layout, cavities=cavities, min_cavity_margin_d=0.25)
        candidates.append({
            "candidate_id": f"DOE-{index:02d}",
            "design": design,
            "geometry_gate_ok": bool(gate["ok"]),
            "geometry_error_count": int(gate["error_count"]),
            "cavity_clearance_min_mm": gate.get("cavity_clearance_min_mm"),
            "physics_prior": prior(design),
            "issues": gate["issues"],
        })
        trials.append({
            "id": len(trials) + 1,
            "design": design,
            "fidelity": config.fidelities[0].name,
            "status": "completed",
            "objective": prior(design),
            "constraints": {"coolant_mass_ratio": 1.0, "loss_ratio": 1.0},
            "relative_cost": 1.0,
        })
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "config": str(Path(args.config).resolve()),
        "seed": config.seed,
        "base_design": str(Path(args.base_design).resolve()),
        "fixed": {
            "diameter_mm": base["geometry"]["diameter_mm"],
            "span_count": base["geometry"]["span_count"],
        },
        "candidates": candidates,
    }, indent=2), encoding="utf-8")
    csv_path = out.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = ["candidate_id", *[v.name for v in config.variables],
                      "geometry_gate_ok", "cavity_clearance_min_mm", "physics_prior"]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for item in candidates:
            writer.writerow({
                "candidate_id": item["candidate_id"],
                **item["design"],
                "geometry_gate_ok": item["geometry_gate_ok"],
                "cavity_clearance_min_mm": item["cavity_clearance_min_mm"],
                "physics_prior": item["physics_prior"],
            })
    print("wrote", out)
    print("wrote", csv_path)
    for item in candidates:
        print(item["candidate_id"], "gate=", item["geometry_gate_ok"],
              "prior=", f'{item["physics_prior"]:.6f}',
              "clearance_mm=", item["cavity_clearance_min_mm"])
    return 0 if all(item["geometry_gate_ok"] for item in candidates) else 2


if __name__ == "__main__":
    raise SystemExit(main())
