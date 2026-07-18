"""Extract coolant-cavity XY sections from the user's external-flow+cavities scdoc.

Runs the extract_cavities journal headless in SpaceClaim and writes the cavity
polygons to configs/c3x_cavities.json (named 3D plenum solids -> role by name).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal

root = Path(__file__).resolve().parents[1]
journal = root / "bofm" / "cad" / "journals" / "extract_cavities.py"

ap = argparse.ArgumentParser()
ap.add_argument("--in-scdoc",
                default=str(root / "runs" / "fluid" / "c3x_external_flow_cavities.scdoc"))
ap.add_argument("--out-json", default=str(root / "configs" / "c3x_cavities.json"))
args = ap.parse_args()

print("extracting cavities from %s ..." % args.in_scdoc, flush=True)
res = run_journal(
    journal,
    env_extra={"BOFM_IN_SCDOC": Path(args.in_scdoc).resolve(),
               "BOFM_OUT_JSON": Path(args.out_json).resolve()},
    headless=True, timeout_s=600,
)
print("returncode:", res.returncode)
print("status:")
print(res.status)
raise SystemExit(0 if res.ok else 1)
