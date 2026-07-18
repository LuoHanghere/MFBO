"""Validate film-cooled fluid topology before SpaceClaim CAD.

Checks that each cylindrical hole segment pierces into its plenum box and that
layout JSON carries precomputed cylinder_mm data for the CAD journal.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from scripts.build_film_layout import build_layout


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(root / "configs" / "c3x_baseline.yaml"))
    ap.add_argument("--layout", default=None, help="Existing layout JSON; rebuild if omitted")
    ap.add_argument("--mode", choices=["unit-cell", "full-span"], default="unit-cell")
    ap.add_argument("--unit-span-mm", type=float, default=20.0)
    args = ap.parse_args()

    if args.layout:
        layout = json.loads(Path(args.layout).read_text(encoding="utf-8"))
    else:
        config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
        layout = build_layout(
            config,
            design=None,
            mode=args.mode,
            unit_span_mm=args.unit_span_mm,
        )

    topo = layout.get("topology", {})
    print("instances:", len(layout.get("instances", [])))
    print("plenums:", [p["id"] for p in layout.get("plenums", [])])
    print("topology ok:", topo.get("ok"))
    for chk in topo.get("plenums", []):
        print(" ", chk["id"], "buried_inside_blade:", chk["corners_inside_blade"])
    for chk in topo.get("instances", []):
        flags = {k: v for k, v in chk.items()
                 if k in ("cylinder_end_inside_plenum", "centerline_pierces_wall_once",
                          "aims_along_design_axis", "error")}
        print(" ", chk.get("id", "?"), flags)

    missing = [i["id"] for i in layout.get("instances", []) if "cylinder_mm" not in i]
    if missing:
        print("missing cylinder_mm:", missing)
        return 2
    if not topo.get("ok", False):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
