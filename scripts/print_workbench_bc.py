"""Print Fluent GUI boundary-condition values for Workbench Route B."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.workbench.bc import format_bc_table


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None, help="Simulation case id from c3x_simulation_cases.yaml")
    ap.add_argument("--out", default=None, help="Optional text file to write")
    args = ap.parse_args()
    text = format_bc_table(args.case)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print("wrote:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
