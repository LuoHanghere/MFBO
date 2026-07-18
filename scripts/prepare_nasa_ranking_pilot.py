"""Create the baseline plus four controlled NASA ranking perturbations."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_c3x_downstream_layout import build_layout
from scripts.validate_workbench_layout import _load_cavities, validate_layout


def design_variables(design: dict) -> dict[str, float]:
    return {
        **{f"{row}_s": float(design["rows"][row]["s_over_s0"])
           for row in ("SS1", "SS2", "PS1", "PS2")},
        "suction_angle_deg": float(
            design["surface_settings"]["suction"]["injection_angle_deg"]
        ),
        "pressure_angle_deg": float(
            design["surface_settings"]["pressure"]["injection_angle_deg"]
        ),
    }


def apply_variables(base: dict, variables: dict[str, float]) -> dict:
    design = json.loads(json.dumps(base))
    for row in ("SS1", "SS2", "PS1", "PS2"):
        design["rows"][row]["s_over_s0"] = variables[f"{row}_s"]
    design["surface_settings"]["suction"]["injection_angle_deg"] = variables[
        "suction_angle_deg"
    ]
    design["surface_settings"]["pressure"]["injection_angle_deg"] = variables[
        "pressure_angle_deg"
    ]
    return design


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-design", required=True)
    parser.add_argument("--cavities", default="configs/c3x_fixed_downstream_plenums.json")
    parser.add_argument("--row-step", type=float, default=0.008)
    parser.add_argument("--angle-step-deg", type=float, default=5.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    base_path = Path(args.base_design).resolve()
    base = json.loads(base_path.read_text(encoding="utf-8"))
    baseline = design_variables(base)
    perturbations = [
        ("BASELINE", "none", {}),
        ("SS_ROWS_DOWN", "SS1_s and SS2_s", {"SS1_s": args.row_step, "SS2_s": args.row_step}),
        ("SS_ANGLE_STEEP", "suction_angle_deg", {"suction_angle_deg": args.angle_step_deg}),
        ("PS_ROWS_DOWN", "PS1_s and PS2_s", {"PS1_s": args.row_step, "PS2_s": args.row_step}),
        ("PS_ANGLE_STEEP", "pressure_angle_deg", {"pressure_angle_deg": args.angle_step_deg}),
    ]
    cavities = _load_cavities(Path(args.cavities).resolve())
    candidates = []
    for candidate_id, changed_variables, deltas in perturbations:
        variables = dict(baseline)
        for name, delta in deltas.items():
            variables[name] += delta
        gate = validate_layout(
            build_layout(apply_variables(base, variables)),
            cavities=cavities,
            min_cavity_margin_d=0.25,
        )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "changed_variables": changed_variables,
                "deltas": deltas,
                "design": variables,
                "geometry_gate_ok": bool(gate["ok"]),
                "geometry_error_count": int(gate["error_count"]),
                "cavity_clearance_min_mm": gate.get("cavity_clearance_min_mm"),
                "issues": gate["issues"],
            }
        )

    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "purpose": "paired coarse/paper ranking and perturbation-direction gate",
                "base_design": str(base_path),
                "row_step": args.row_step,
                "angle_step_deg": args.angle_step_deg,
                "candidates": candidates,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    designs_dir = output.parent / "designs"
    designs_dir.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        (designs_dir / f'{candidate["candidate_id"]}.json').write_text(
            json.dumps(candidate["design"], indent=2), encoding="utf-8"
        )
    with output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as stream:
        fieldnames = [
            "candidate_id", "changed_variables", *baseline,
            "geometry_gate_ok", "cavity_clearance_min_mm",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "candidate_id": candidate["candidate_id"],
                    "changed_variables": candidate["changed_variables"],
                    **candidate["design"],
                    "geometry_gate_ok": candidate["geometry_gate_ok"],
                    "cavity_clearance_min_mm": candidate["cavity_clearance_min_mm"],
                }
            )
    for candidate in candidates:
        print(
            candidate["candidate_id"],
            "gate=", candidate["geometry_gate_ok"],
            "clearance_mm=", candidate["cavity_clearance_min_mm"],
        )
    return 0 if all(candidate["geometry_gate_ok"] for candidate in candidates) else 2


if __name__ == "__main__":
    raise SystemExit(main())
