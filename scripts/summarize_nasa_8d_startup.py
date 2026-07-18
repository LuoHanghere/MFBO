"""Summarize completed 8D NASA startup trials from the optimization ledger."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default="runs/optimization/nasa_standard_mfbo_8d/"
        "c3x_nasa_standard_mfbo_8d.sqlite3",
    )
    parser.add_argument(
        "--out-dir",
        default="runs/optimization/nasa_standard_mfbo_8d/startup_summary",
    )
    parser.add_argument("--baseline-objective", type=float, required=True)
    parser.add_argument("--baseline-diameter-mm", type=float, default=0.99)
    parser.add_argument("--baseline-span-count", type=int, default=5)
    parser.add_argument("--source", default="stratified_startup")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, design_json, fidelity, source, objective, constraints_json,
                   metrics_json, relative_cost, run_dir
            FROM trials
            WHERE status = 'completed'
              AND source = ?
              AND json_extract(design_json, '$.diameter_mm') IS NOT NULL
              AND json_extract(design_json, '$.span_count') IS NOT NULL
            ORDER BY id
            """,
            (args.source,),
        ).fetchall()

    baseline_area_factor = (
        args.baseline_span_count * args.baseline_diameter_mm**2
    )
    records = []
    for row in rows:
        design = json.loads(row[1])
        constraints = json.loads(row[5] or "{}")
        metrics = json.loads(row[6] or "{}")
        objective = float(row[4])
        diameter = float(design["diameter_mm"])
        span_count = int(round(float(design["span_count"])))
        records.append(
            {
                "trial_id": int(row[0]),
                "candidate": f"N{span_count}",
                "fidelity": row[2],
                "source": row[3],
                "diameter_mm": diameter,
                "span_count": span_count,
                "open_area_ratio": span_count * diameter**2 / baseline_area_factor,
                "objective": objective,
                "change_vs_baseline_pct": 100.0
                * (objective / args.baseline_objective - 1.0),
                "whole_vane_eta_bar": metrics.get("whole_vane_eta_bar"),
                "coolant_mass_ratio": constraints.get("coolant_mass_ratio"),
                "continuity_residual": metrics.get("continuity_residual"),
                "y_plus_p95": metrics.get("y_plus_p95"),
                "y_plus_max": metrics.get("y_plus_max"),
                "relative_cost": float(row[7]),
                "run_dir": row[8],
            }
        )

    if not records:
        raise RuntimeError("no completed 8D startup trials found")

    csv_path = out_dir / "startup_trials.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    best = max(records, key=lambda record: record["objective"])
    payload = {
        "database": str(db_path),
        "source": args.source,
        "baseline": {
            "objective": args.baseline_objective,
            "diameter_mm": args.baseline_diameter_mm,
            "span_count": args.baseline_span_count,
        },
        "completed_8d_trials": len(records),
        "incremental_relative_cost": sum(
            record["relative_cost"] for record in records
        ),
        "best": best,
        "trials": records,
        "interpretation_note": (
            "Open-area ratio is descriptive only because the other six design "
            "variables also vary between startup points."
        ),
    }
    json_path = out_dir / "startup_summary.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    fig, axis = plt.subplots(figsize=(8.6, 5.4), constrained_layout=True)
    points = sorted(records, key=lambda record: record["open_area_ratio"])
    axis.plot(
        [record["open_area_ratio"] for record in points],
        [record["objective"] for record in points],
        color="#4c78a8",
        linewidth=1.5,
        alpha=0.7,
    )
    scatter = axis.scatter(
        [record["open_area_ratio"] for record in points],
        [record["objective"] for record in points],
        c=[record["span_count"] for record in points],
        cmap="viridis",
        s=78,
        edgecolor="black",
        linewidth=0.6,
        zorder=3,
    )
    for record in points:
        axis.annotate(
            f"N={record['span_count']}, D={record['diameter_mm']:.3f}",
            (record["open_area_ratio"], record["objective"]),
            xytext=(5, 7),
            textcoords="offset points",
            fontsize=8.5,
        )
    axis.axhline(
        args.baseline_objective,
        color="#e45756",
        linestyle="--",
        linewidth=1.4,
        label=f"coarse baseline = {args.baseline_objective:.5f}",
    )
    axis.axvline(1.0, color="#777777", linestyle=":", linewidth=1.0)
    axis.set_xlabel("Total film-hole open-area ratio to baseline")
    axis.set_ylabel("Protected-area cooling effectiveness")
    axis.set_title("NASA 8D MFBO startup stratum (L2)")
    axis.grid(True, alpha=0.22)
    axis.legend(loc="best")
    colorbar = fig.colorbar(scatter, ax=axis, pad=0.02)
    colorbar.set_label("Spanwise hole count per row")
    figure_path = out_dir / "objective_vs_open_area_ratio.png"
    fig.savefig(figure_path, dpi=190)
    plt.close(fig)

    print(json.dumps({
        "csv": str(csv_path),
        "json": str(json_path),
        "figure": str(figure_path),
        "best_trial": best["trial_id"],
        "best_objective": best["objective"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
