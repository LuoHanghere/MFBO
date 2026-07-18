"""CLI: build the Kumar/NASA flow domain and unmerged film-hole markers."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_SCRIPT = ROOT / "scripts" / "build_c3x_kumar_paper_layout.py"
FLOW_JOURNAL = ROOT / "bofm" / "cad" / "journals" / "build_external_flow_domain.py"
CAVITY_FLOW_JOURNAL = ROOT / "bofm" / "cad" / "journals" / "build_external_flow_with_cavities.py"
MARKER_JOURNAL = ROOT / "bofm" / "cad" / "journals" / "add_c3x_kumar_paper_hole_markers.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", type=int, choices=range(1, 7), default=1)
    parser.add_argument("--pressure-angle-deg", type=float)
    parser.add_argument("--suction-angle-deg", type=float)
    parser.add_argument("--orientation", choices=("forward", "reverse"))
    parser.add_argument("--out-prefix", default=str(ROOT / "runs" / "fluid" / "c3x_kumar_case1"))
    parser.add_argument(
        "--cavities-json",
        default=str(ROOT / "configs" / "c3x_cavities.json"),
        help="Full cavity source; its fixed leading-edge cavity is retained",
    )
    parser.add_argument(
        "--downstream-cavities-json",
        default=str(ROOT / "configs" / "c3x_fixed_downstream_plenums.json"),
        help="Reviewed SS/PS plenums used by the mandatory geometry gate",
    )
    args = parser.parse_args()

    layout_json = ROOT / "configs" / "c3x_kumar_paper_hole_markers.json"
    layout_csv = ROOT / "configs" / "c3x_kumar_paper_hole_markers.csv"
    layout_png = ROOT / "configs" / "c3x_kumar_paper_hole_markers.png"
    layout_le_csv = ROOT / "configs" / "c3x_kumar_paper_le_hole_markers.csv"
    layout_le_png = ROOT / "configs" / "c3x_kumar_paper_le_stagger.png"
    flow_json = ROOT / "configs" / "c3x_kumar_paper_external_flow.json"
    cmd = [
        sys.executable,
        str(LAYOUT_SCRIPT),
        "--case-id", str(args.case_id),
        "--out-json", str(layout_json),
        "--out-csv", str(layout_csv),
        "--out-png", str(layout_png),
        "--out-le-csv", str(layout_le_csv),
        "--out-le-png", str(layout_le_png),
        "--external-flow-json", str(flow_json),
    ]
    if args.pressure_angle_deg is not None:
        cmd.extend(["--pressure-angle-deg", str(args.pressure_angle_deg)])
    if args.suction_angle_deg is not None:
        cmd.extend(["--suction-angle-deg", str(args.suction_angle_deg)])
    if args.orientation is not None:
        cmd.extend(["--orientation", args.orientation])
    subprocess.run(cmd, cwd=ROOT, check=True)

    layout = json.loads(layout_json.read_text(encoding="utf-8"))
    span_mm = float(layout["geometry"]["periodic_span_mm"])
    prefix = Path(args.out_prefix).resolve()
    base_scdoc = prefix.with_name(prefix.name + "_external_flow.scdoc")
    marker_scdoc = prefix.with_name(prefix.name + "_hole_markers_unmerged.scdoc")

    print("building corrected NASA C3X external flow ...", flush=True)
    cavities_json = Path(args.cavities_json).resolve() if args.cavities_json else None
    downstream_cavities_json = (
        Path(args.downstream_cavities_json).resolve()
        if args.downstream_cavities_json else None
    )
    if cavities_json and downstream_cavities_json:
        if not cavities_json.is_file():
            raise FileNotFoundError(cavities_json)
        if not downstream_cavities_json.is_file():
            raise FileNotFoundError(downstream_cavities_json)
        full_cavities = json.loads(cavities_json.read_text(encoding="utf-8"))
        downstream_cavities = json.loads(
            downstream_cavities_json.read_text(encoding="utf-8")
        )
        leading_edge = [
            cavity for cavity in full_cavities["cavities"]
            if cavity.get("role") == "LE_plenum"
        ]
        reviewed_downstream = [
            cavity for cavity in downstream_cavities["cavities"]
            if cavity.get("role") in {"SS_plenum", "PS_plenum"}
        ]
        if len(leading_edge) != 1 or len(reviewed_downstream) != 2:
            raise ValueError("expected one LE and two reviewed downstream plenums")
        merged_cavities = {
            "source": {
                "leading_edge": str(cavities_json),
                "downstream": str(downstream_cavities_json),
            },
            "cavities": reviewed_downstream + leading_edge,
        }
        cavities_json = prefix.with_name(prefix.name + "_cavities.json")
        cavities_json.write_text(json.dumps(merged_cavities, indent=2), encoding="utf-8")
    flow_journal = CAVITY_FLOW_JOURNAL if cavities_json else FLOW_JOURNAL
    flow_env = {
        "BOFM_EXTERNAL_FLOW_JSON": str(flow_json.resolve()),
        "BOFM_SPAN_MM": str(span_mm),
    }
    if cavities_json:
        flow_env["BOFM_CAVITIES_JSON"] = str(cavities_json)
    flow_result = run_journal(
        flow_journal,
        out_scdoc=base_scdoc,
        env_extra=flow_env,
        headless=True,
        timeout_s=900,
    )
    print(flow_result.status)
    if not flow_result.ok:
        return 1

    print("adding independent downstream and leading-edge cylinders ...", flush=True)
    marker_result = run_journal(
        MARKER_JOURNAL,
        out_scdoc=marker_scdoc,
        env_extra={
            "BOFM_IN_SCDOC": str(base_scdoc),
            "BOFM_KUMAR_LAYOUT_JSON": str(layout_json.resolve()),
        },
        headless=True,
        timeout_s=900,
    )
    print(marker_result.status)
    print("external flow:", base_scdoc)
    print("cavities:", cavities_json if cavities_json else "not included")
    print("unmerged markers:", marker_scdoc)
    return 0 if marker_result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
