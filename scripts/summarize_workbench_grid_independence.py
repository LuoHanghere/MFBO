"""Summarize Workbench Route B grid-independence manifests."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


TIER_ORDER = {"smoke": 0, "coarse": 1, "paper": 2, "fine": 3}


def get(d: dict[str, Any] | None, path: str, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return f"{v:.6g}"
    return str(v)


def row_from_manifest(path: Path) -> dict[str, Any]:
    m = json.loads(path.read_text(encoding="utf-8"))
    pressure_loss = get(m, "result_summary.pressure_loss")
    return {
        "tier": m.get("mesh_tier"),
        "name": m.get("name"),
        "topology_ok": get(m, "status.topology_ok"),
        "post_valid": get(m, "status.post_valid"),
        "cell_count": get(m, "mesh_summary.cell_count"),
        "eta_bar": get(m, "result_summary.eta_bar"),
        "protected_eta_bar": get(m, "result_summary.protected_eta_bar"),
        "nasa_pressure_rmse": get(m, "result_summary.nasa_surface_pressure.rmse"),
        "nasa_pressure_side_rmse": get(m, "result_summary.nasa_surface_pressure.sides.pressure.rmse"),
        "nasa_suction_side_rmse": get(m, "result_summary.nasa_surface_pressure.sides.suction.rmse"),
        "coolant_mass_flow_ratio": get(m, "result_summary.coolant_mass_flow_ratio"),
        "mass_imbalance_kg_s": get(m, "result_summary.mass_imbalance"),
        "delta_total_pressure_Pa": get(pressure_loss, "delta_total_pressure_Pa") if isinstance(pressure_loss, dict) else None,
        "y_plus_p95": get(m, "result_summary.y_plus_p95"),
        "y_plus_max": get(m, "result_summary.y_plus_max"),
        "continuity": get(m, "result_summary.last_residual_row.continuity"),
        "energy": get(m, "result_summary.last_residual_row.energy"),
        "artificial_wall_warnings": get(m, "result_summary.warnings.artificial_wall"),
        "reversed_flow_warnings": get(m, "result_summary.warnings.reversed_flow"),
        "manifest": str(path.resolve()),
    }


def markdown_table(rows: list[dict[str, Any]]) -> str:
    cols = [
        "tier", "cell_count", "nasa_pressure_rmse", "nasa_pressure_side_rmse",
        "nasa_suction_side_rmse", "eta_bar", "protected_eta_bar",
        "coolant_mass_flow_ratio", "mass_imbalance_kg_s",
        "delta_total_pressure_Pa", "y_plus_p95", "continuity",
        "artificial_wall_warnings", "reversed_flow_warnings",
    ]
    out = []
    out.append("| " + " | ".join(cols) + " |")
    out.append("| " + " | ".join("---" for _ in cols) + " |")
    for row in rows:
        out.append("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="runs/workbench/grid_independence")
    ap.add_argument("--pattern", default="**/*_manifest.json")
    ap.add_argument("--out-csv", default="runs/workbench/grid_independence/grid_independence_summary.csv")
    ap.add_argument("--out-md", default="runs/workbench/grid_independence/grid_independence_summary.md")
    args = ap.parse_args()

    root = Path(args.root)
    manifests = sorted(
        root.glob(args.pattern),
        key=lambda p: (TIER_ORDER.get(p.parent.name, 99), str(p)),
    )
    rows = [row_from_manifest(p) for p in manifests]
    rows.sort(key=lambda r: (TIER_ORDER.get(str(r.get("tier")), 99), str(r.get("name"))))

    out_csv = Path(args.out_csv)
    out_md = Path(args.out_md)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        out_csv.write_text("", encoding="utf-8")
    out_md.write_text(markdown_table(rows) if rows else "_No manifests found._\n", encoding="utf-8")

    print("manifests:", len(rows))
    print("wrote:", out_csv)
    print("wrote:", out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
