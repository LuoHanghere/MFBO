"""Refresh convergence diagnostics in an existing post directory from a log."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_workbench_film_results import parse_convergence_log


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-dir", required=True)
    parser.add_argument("--log", required=True)
    args = parser.parse_args()

    post_dir = Path(args.post_dir)
    convergence = parse_convergence_log(Path(args.log))
    (post_dir / "convergence_summary.json").write_text(
        json.dumps(convergence, indent=2), encoding="utf-8"
    )
    bo_path = post_dir / "bo_summary.json"
    bo_summary = json.loads(bo_path.read_text(encoding="utf-8"))
    bo_summary.setdefault("diagnostics", {})["convergence"] = convergence
    bo_path.write_text(json.dumps(bo_summary, indent=2), encoding="utf-8")
    print("wrote:", post_dir / "convergence_summary.json")
    print("updated:", bo_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
