"""Scan conditional C3X row-position ranges against the fixed SS/PS plenums.

Each row is varied while the other design variables remain at baseline.  The
result is a useful initial BO box, not a replacement for the per-candidate
geometry gate because paired rows share their injection-axis frame.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from scripts.build_c3x_downstream_layout import ROW_ORDER, build_layout
from scripts.validate_workbench_layout import _load_cavities, validate_layout


ROOT = Path(__file__).resolve().parents[1]


def _intervals(values: list[float], step: float) -> list[list[float]]:
    if not values:
        return []
    out: list[list[float]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value - previous > 1.5 * step:
            out.append([start, previous])
            start = value
        previous = value
    out.append([start, previous])
    return out


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
    parser.add_argument("--s-min", type=float, default=0.10)
    parser.add_argument("--s-max", type=float, default=0.40)
    parser.add_argument("--step", type=float, default=0.001)
    parser.add_argument("--margin-d", type=float, default=0.25)
    parser.add_argument(
        "--out-json",
        default=str(ROOT / "configs" / "c3x_row_feasible_ranges_baseline_angles.json"),
    )
    args = parser.parse_args()

    design_path = Path(args.design).resolve()
    cavity_path = Path(args.cavities).resolve()
    design = json.loads(design_path.read_text(encoding="utf-8"))
    cavities = _load_cavities(cavity_path)
    samples = np.arange(args.s_min, args.s_max + 0.5 * args.step, args.step)
    rows: dict[str, dict] = {}

    for row_id in ROW_ORDER:
        feasible: list[float] = []
        rejected = 0
        for sample in samples:
            trial = copy.deepcopy(design)
            trial["rows"][row_id]["s_over_s0"] = float(sample)
            try:
                layout = build_layout(trial)
                result = validate_layout(
                    layout,
                    cavities=cavities,
                    min_cavity_margin_d=args.margin_d,
                )
                if result["ok"]:
                    feasible.append(round(float(sample), 12))
                else:
                    rejected += 1
            except (ValueError, KeyError):
                rejected += 1

        intervals = _intervals(feasible, args.step)
        baseline = float(design["rows"][row_id]["s_over_s0"])
        containing = next(
            (interval for interval in intervals if interval[0] <= baseline <= interval[1]),
            None,
        )
        rows[row_id] = {
            "surface": design["rows"][row_id]["surface"],
            "baseline_s_over_s0": baseline,
            "feasible_intervals": intervals,
            "baseline_interval": containing,
            "feasible_sample_count": len(feasible),
            "rejected_sample_count": rejected,
        }

    output = {
        "status": "ok",
        "method": "one-row-at-a-time conditional scan; all other variables held at baseline",
        "design": str(design_path),
        "cavities": str(cavity_path),
        "scan": {
            "s_min": args.s_min,
            "s_max": args.s_max,
            "step": args.step,
            "additional_cavity_margin_D": args.margin_d,
        },
        "fixed_angles_deg": {
            name: float(spec["injection_angle_deg"])
            for name, spec in design["surface_settings"].items()
        },
        "rows": rows,
        "warning": (
            "These are conditional ranges, not independent guaranteed bounds. "
            "Paired rows share an injection-axis frame; every BO candidate must "
            "still pass validate_workbench_layout.py with the current cavities."
        ),
    }
    out = Path(args.out_json).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
