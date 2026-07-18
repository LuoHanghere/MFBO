"""Export body/face bounding boxes from a C3X SCDOC without modifying it."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal


ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "bofm" / "cad" / "journals" / "inspect_c3x_boundary_faces.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-scdoc", required=True)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()
    out = Path(args.out_json).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    result = run_journal(
        JOURNAL,
        env_extra={
            "BOFM_IN_SCDOC": str(Path(args.in_scdoc).resolve()),
            "BOFM_OUT_JSON": str(out),
        },
        headless=True,
        timeout_s=600,
    )
    print(result.status)
    print("json:", out)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
