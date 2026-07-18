"""Build Workbench Route B geometry only (SCDOC for Discovery — no SAT mesh)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "python.exe"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Parametric geometry for Workbench Discovery (mesh in GUI, not SAT)",
    )
    ap.add_argument("--name", required=True, help="Folder under runs/workbench/")
    ap.add_argument("--gui", action="store_true", help="SpaceClaim with UI")
    ap.add_argument("--ss1-s", type=float)
    ap.add_argument("--ss2-s", type=float)
    ap.add_argument("--ps1-s", type=float)
    ap.add_argument("--ps2-s", type=float)
    args = ap.parse_args()

    prefix = ROOT / "runs" / "workbench" / args.name / f"c3x_wb_{args.name}"
    cmd = [str(PY), str(ROOT / "scripts" / "build_c3x_workbench_case.py"),
           "--out-prefix", str(prefix)]
    for flag, val in (
        ("--ss1-s", args.ss1_s), ("--ss2-s", args.ss2_s),
        ("--ps1-s", args.ps1_s), ("--ps2-s", args.ps2_s),
    ):
        if val is not None:
            cmd.extend([flag, str(val)])
    if args.gui:
        cmd.append("--gui")

    rc = subprocess.call(cmd)
    if rc != 0:
        return rc

    print("\n--- Next: Workbench GUI (Route B) ---", flush=True)
    print("1. Open 1.wbpj (Discovery + Fluent system)", flush=True)
    print(f"2. Discovery Geometry -> open {prefix}.scdoc", flush=True)
    print("3. Update -> transfer to Fluent Meshing", flush=True)
    print("4. UseBodyLabels=Yes, Update Boundaries, volume mesh, Switch to Solution", flush=True)
    print("5. run_workbench_film_setup.py --case-in <your FLTG-2.cas.h5>", flush=True)
    print("6. run_workbench_film_iterate.py --cores 10", flush=True)
    print("Do NOT use .sat or split_merged_boundary on this machine.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
