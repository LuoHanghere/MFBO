"""Audit the sensitivity of area-weighted effectiveness to local clipping."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-dir", action="append", required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if len(args.post_dir) != len(args.label):
        parser.error("--post-dir and --label counts must match")

    audits = []
    for label, post_dir_text in zip(args.label, args.post_dir):
        post_dir = Path(post_dir_text)
        bo_summary = json.loads((post_dir / "bo_summary.json").read_text(encoding="utf-8"))
        tg_ref = float(bo_summary["references"]["Tg_ref_K"])
        tc_ref = float(bo_summary["references"]["Tc_ref"]["value_K"])
        with (post_dir / "eta_surface_faces.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        values = [
            (float(row["face_area_m2"]), float(row["eta"]), float(row["Taw_K"]))
            for row in rows
        ]
        total_area = sum(area for area, _, _ in values)
        raw_eta = sum(area * eta for area, eta, _ in values) / total_area
        clipped_eta = sum(area * min(1.0, max(0.0, eta)) for area, eta, _ in values) / total_area
        audits.append(
            {
                "label": label,
                "face_count": len(values),
                "area_m2": total_area,
                "raw_eta_bar": raw_eta,
                "clipped_eta_bar": clipped_eta,
                "absolute_change": clipped_eta - raw_eta,
                "relative_change_pct": 100.0 * (clipped_eta - raw_eta) / raw_eta,
                "eta_outside_0_1_area_fraction": sum(
                    area for area, eta, _ in values if eta < 0.0 or eta > 1.0
                ) / total_area,
                "taw_above_tg_area_fraction": sum(
                    area for area, _, taw in values if taw > tg_ref
                ) / total_area,
                "taw_below_tc_area_fraction": sum(
                    area for area, _, taw in values if taw < tc_ref
                ) / total_area,
                "Tg_ref_K": tg_ref,
                "Tc_ref_K": tc_ref,
                "post_dir": str(post_dir.resolve()),
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"audits": audits}, indent=2), encoding="utf-8")
    print("wrote:", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
