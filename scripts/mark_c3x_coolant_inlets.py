"""Create coolant inlet named selections on the fixed-LE C3X models."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal


ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "bofm" / "cad" / "journals" / "mark_c3x_coolant_inlets.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-scdoc", default=str(ROOT / "runs" / "fluid" / "c3x_kumar_fixed_le_template.scdoc"))
    parser.add_argument("--out-scdoc", default=str(ROOT / "runs" / "fluid" / "c3x_kumar_fixed_le_template_named.scdoc"))
    parser.add_argument("--targets", default=str(ROOT / "configs" / "c3x_boundary_targets.json"))
    args = parser.parse_args()
    output = Path(args.out_scdoc).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    result = run_journal(
        JOURNAL,
        out_scdoc=output,
        env_extra={
            "BOFM_IN_SCDOC": str(Path(args.in_scdoc).resolve()),
            "BOFM_BOUNDARY_TARGETS_JSON": str(Path(args.targets).resolve()),
        },
        headless=True,
        timeout_s=600,
    )
    print(result.status)
    print("output:", output)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
