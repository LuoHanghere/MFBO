"""Extrude the external-flow domain + extracted coolant cavities to full span.

Inputs (already generated):
  configs/c3x_external_flow.json   duct boundary + vane cutout (check_external_flow.py)
  configs/c3x_cavities.json        plenum sections extracted from the user's .scdoc
Produces runs/fluid/c3x_external_flow_cavities.scdoc with bodies:
  fluid + SS_plenum + PS_plenum + LE_plenum, and the flow named selections.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal

root = Path(__file__).resolve().parents[1]
journal = root / "bofm" / "cad" / "journals" / "build_external_flow_with_cavities.py"

ap = argparse.ArgumentParser()
ap.add_argument("--span-mm", type=float, default=76.2, help="full vane height by default")
ap.add_argument("--out", default=str(root / "runs" / "fluid" / "c3x_external_flow_cavities.scdoc"))
args = ap.parse_args()

print("building external flow + coolant cavities, span=%.1f mm ..." % args.span_mm, flush=True)
res = run_journal(
    journal,
    out_scdoc=Path(args.out),
    env_extra={
        "BOFM_EXTERNAL_FLOW_JSON": (root / "configs" / "c3x_external_flow.json").resolve(),
        "BOFM_CAVITIES_JSON": (root / "configs" / "c3x_cavities.json").resolve(),
        "BOFM_SPAN_MM": args.span_mm,
    },
    headless=True, timeout_s=600,
)
print("returncode:", res.returncode)
print("scdoc:", res.out_scdoc, "exists:", res.out_scdoc.exists() if res.out_scdoc else None)
print("status:")
print(res.status)
raise SystemExit(0 if res.ok else 1)
