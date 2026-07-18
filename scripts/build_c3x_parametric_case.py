"""CLI: resolve downstream design, build cylinders, and create one fluid body."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal
from scripts.build_c3x_downstream_layout import build_layout, write_csv, write_plot


ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "bofm" / "cad" / "journals" / "build_c3x_parametric_downstream_case.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", default=str(ROOT / "configs" / "c3x_downstream_design_baseline.json"))
    parser.add_argument("--template", default=str(ROOT / "runs" / "fluid" / "c3x_kumar_fixed_le_template.scdoc"))
    parser.add_argument("--out-prefix", default=str(ROOT / "runs" / "parametric" / "baseline" / "c3x_baseline"))
    parser.add_argument("--ss1-s", type=float)
    parser.add_argument("--ss2-s", type=float)
    parser.add_argument("--ps1-s", type=float)
    parser.add_argument("--ps2-s", type=float)
    parser.add_argument("--suction-angle", type=float)
    parser.add_argument("--pressure-angle", type=float)
    parser.add_argument("--suction-orientation", choices=("forward", "reverse"))
    parser.add_argument("--pressure-orientation", choices=("forward", "reverse"))
    parser.add_argument("--diameter-mm", type=float)
    parser.add_argument("--span-count", type=int)
    args = parser.parse_args()

    design = json.loads(Path(args.design).read_text(encoding="utf-8"))
    for row_id, value in (("SS1", args.ss1_s), ("SS2", args.ss2_s),
                          ("PS1", args.ps1_s), ("PS2", args.ps2_s)):
        if value is not None:
            design["rows"][row_id]["s_over_s0"] = value
    for surface, angle, orientation in (
        ("suction", args.suction_angle, args.suction_orientation),
        ("pressure", args.pressure_angle, args.pressure_orientation),
    ):
        if angle is not None:
            design["surface_settings"][surface]["injection_angle_deg"] = angle
        if orientation is not None:
            design["surface_settings"][surface]["orientation"] = orientation
    if args.diameter_mm is not None:
        design["geometry"]["diameter_mm"] = args.diameter_mm
    if args.span_count is not None:
        design["geometry"]["span_count"] = args.span_count

    prefix = Path(args.out_prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    resolved_design = prefix.with_name(prefix.name + "_design.json")
    layout_json = prefix.with_name(prefix.name + "_layout.json")
    layout_csv = prefix.with_name(prefix.name + "_layout.csv")
    layout_png = prefix.with_name(prefix.name + "_layout.png")
    out_scdoc = prefix.with_suffix(".scdoc")
    resolved_design.write_text(json.dumps(design, indent=2), encoding="utf-8")
    layout = build_layout(design)
    layout_json.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    write_csv(layout_csv, layout)
    write_plot(layout_png, layout)

    result = run_journal(
        JOURNAL,
        out_scdoc=out_scdoc,
        env_extra={
            "BOFM_IN_SCDOC": str(Path(args.template).resolve()),
            "BOFM_DOWNSTREAM_LAYOUT_JSON": str(layout_json),
            "BOFM_BOUNDARY_TARGETS_JSON": str((ROOT / "configs" / "c3x_boundary_targets.json").resolve()),
            "BOFM_PASSAGE_JSON": str((ROOT / "configs" / "c3x_kumar_paper_external_flow.json").resolve()),
        },
        headless=True,
        timeout_s=900,
    )
    print(result.status)
    print("design:", resolved_design)
    print("layout:", layout_json)
    print("model:", out_scdoc)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
