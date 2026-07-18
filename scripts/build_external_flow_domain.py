"""Extrude the single-airfoil external-flow domain in SpaceClaim.

Produces the FIXED fluid domain (vane cut out of the periodic duct, extruded to
span) that you open in SpaceClaim to draw the coolant plenums. Film holes are
added afterwards by a separate parametric journal.

Run check_external_flow.py first to (re)generate configs/c3x_external_flow.json.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal

root = Path(__file__).resolve().parents[1]
journal = root / "bofm" / "cad" / "journals" / "build_external_flow_domain.py"
ef_json = root / "configs" / "c3x_external_flow.json"

ap = argparse.ArgumentParser()
ap.add_argument("--span-mm", type=float, default=3.96,
                help="spanwise extrusion depth (default 3.96 = one baseline hole "
                     "pitch p/D=4, D=0.99; use 76.2 for the full vane height)")
ap.add_argument("--out", default=str(root / "runs" / "fluid" / "c3x_external_flow.scdoc"))
args = ap.parse_args()

out = Path(args.out)
print("building single-airfoil external-flow domain in SpaceClaim ...", flush=True)
print("  json :", ef_json)
print("  span :", args.span_mm, "mm")
res = run_journal(
    journal,
    out_scdoc=out,
    env_extra={"BOFM_EXTERNAL_FLOW_JSON": ef_json.resolve(),
               "BOFM_SPAN_MM": args.span_mm},
    headless=True,
    timeout_s=600,
)

print("returncode:", res.returncode)
print("scdoc:", res.out_scdoc, "exists:", res.out_scdoc.exists() if res.out_scdoc else None)
print("status:")
print(res.status)
raise SystemExit(0 if res.ok else 1)
