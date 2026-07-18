"""Build a Workbench-ready C3X case (fixed LE + parametric downstream holes).

Outputs a single-body SCDOC with Discovery/Fluent face labels:
  inlet, outlet, periodic_*, span_*, vane_wall, film_hole_wall, qian, ss, ps

Body name: fixed_fluid_domain (matches 1.wbpj / FLTG.wft).

The generated SCDOC is consumed directly by the native-CAD Fluent meshing
route documented in docs/c3x_native_cad_route.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal
from scripts.build_c3x_downstream_layout import build_layout, write_csv, write_plot
from scripts.validate_workbench_layout import _load_cavities, validate_layout


ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "bofm" / "cad" / "journals" / "build_c3x_parametric_downstream_case.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Workbench Route B geometry builder")
    parser.add_argument("--design", default=str(ROOT / "configs" / "c3x_downstream_design_baseline.json"))
    parser.add_argument(
        "--template",
        default=os.environ.get(
            "BOFM_C3X_TEMPLATE",
            str(ROOT / "runs" / "fluid" / "c3x_kumar_fixed_le_template.scdoc"),
        ),
    )
    parser.add_argument(
        "--targets",
        default=str(ROOT / "configs" / "c3x_boundary_targets.json"),
        help="Coolant-inlet face target definitions",
    )
    parser.add_argument(
        "--cavities",
        default=str(ROOT / "configs" / "c3x_fixed_downstream_plenums.json"),
        help="SS/PS plenum polygons in the same coordinate frame as the layout",
    )
    parser.add_argument(
        "--min-cavity-margin-d",
        type=float,
        default=0.25,
        help="Required plenum-wall margin beyond the hole radius, in D",
    )
    parser.add_argument("--out-prefix", default=str(ROOT / "runs" / "workbench" / "baseline" / "c3x_wb_baseline"))
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
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch SpaceClaim with UI (use when headless batch fails on this machine)",
    )
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
    gate_json = prefix.with_name(prefix.name + "_geometry_gate.json")
    out_scdoc = prefix.with_suffix(".scdoc")
    manifest = prefix.with_name(prefix.name + "_workbench_manifest.json")

    resolved_design.write_text(json.dumps(design, indent=2), encoding="utf-8")
    layout = build_layout(design)
    layout_json.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    write_csv(layout_csv, layout)
    write_plot(layout_png, layout)

    cavities_path = Path(args.cavities).resolve()
    if not cavities_path.is_file():
        raise FileNotFoundError(
            f"plenum geometry gate requires cavity polygons: {cavities_path}"
        )
    gate = validate_layout(
        layout,
        cavities=_load_cavities(cavities_path),
        min_cavity_margin_d=args.min_cavity_margin_d,
    )
    gate.update({
        "design_json": str(resolved_design),
        "layout_json": str(layout_json),
        "cavities_json": str(cavities_path),
        "min_cavity_margin_d": args.min_cavity_margin_d,
    })
    gate_json.write_text(json.dumps(gate, indent=2), encoding="utf-8")
    if not gate["ok"]:
        print("GEOMETRY_GATE_REJECTED", flush=True)
        print("geometry gate:", gate_json, flush=True)
        for issue in gate["issues"][:20]:
            print(issue["level"].upper(), issue["kind"], issue.get("row_id", ""), issue["message"])
        return 2

    result = run_journal(
        JOURNAL,
        out_scdoc=out_scdoc,
        env_extra={
            "BOFM_IN_SCDOC": str(Path(args.template).resolve()),
            "BOFM_DOWNSTREAM_LAYOUT_JSON": str(layout_json),
            "BOFM_BOUNDARY_TARGETS_JSON": str(Path(args.targets).resolve()),
            "BOFM_PASSAGE_JSON": str((ROOT / "configs" / "c3x_kumar_paper_external_flow.json").resolve()),
            "BOFM_BOUNDARY_STYLE": "workbench",
            "BOFM_EXPORT_SAT": "0",
        },
        headless=not args.gui,
        timeout_s=900,
    )

    manifest.write_text(
        json.dumps(
            {
                "route": "workbench",
                "body_name": "fixed_fluid_domain",
                "face_zones": [
                    "inlet", "outlet", "periodic_low", "periodic_high",
                    "span_low", "span_high", "vane_wall", "film_hole_wall",
                    "qian", "ss", "ps",
                ],
                "design_json": str(resolved_design),
                "layout_json": str(layout_json),
                "boundary_targets_json": str(Path(args.targets).resolve()),
                "cavities_json": str(cavities_path),
                "geometry_gate_json": str(gate_json),
                "geometry_gate_ok": gate["ok"],
                "min_cavity_margin_d": args.min_cavity_margin_d,
                "scdoc": str(out_scdoc),
                "spaceclaim_ok": result.ok,
                "next_steps": [
                    "Open *.scdoc in Workbench Discovery (NOT SAT — labels are lost in SAT)",
                    "Transfer geometry to Fluent Meshing; UseBodyLabels=Yes, LengthUnit=m",
                    "Update Boundaries: qian/ss/ps -> pressure-inlet; pair periodic_low/high",
                    "Switch to Solution; write FLTG-2.cas.h5",
                    "Run run_workbench_film_setup.py then run_workbench_film_iterate.py (no split)",
                    "BC values: scripts/print_workbench_bc.py",
                ],
                "do_not_use": [
                    "build_c3x_parametric_mesh.py / .sat import",
                    "split_merged_boundary / sep_face_zone_angle",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(result.status)
    print("design:", resolved_design)
    print("layout:", layout_json)
    print("geometry gate:", gate_json)
    print("model:", out_scdoc)
    print("manifest:", manifest)
    if not result.ok:
        print("hint: retry with --gui if headless SpaceClaim fails on this machine", flush=True)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
