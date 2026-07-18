"""Open an existing SpaceClaim SCDOC and save/export it under a standard name."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal

root = Path(__file__).resolve().parents[1]
journal = root / "bofm" / "cad" / "journals" / "export_existing_scdoc.py"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-scdoc", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    res = run_journal(
        journal,
        out_scdoc=Path(args.out),
        env_extra={"BOFM_IN_SCDOC": str(Path(args.in_scdoc).resolve())},
        headless=True,
        timeout_s=900,
    )
    print("returncode:", res.returncode)
    print("scdoc:", res.out_scdoc, "exists:", res.out_scdoc.exists() if res.out_scdoc else None)
    print("status:")
    print(res.status)
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
