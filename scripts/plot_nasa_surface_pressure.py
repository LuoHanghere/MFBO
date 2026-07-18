"""Plot CFD versus NASA CR-182133 Table VII surface pressure."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison-csv", action="append", required=True)
    parser.add_argument("--label", action="append")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    datasets = []
    labels = args.label or []
    colors = ("#d1493f", "#2563eb", "#16845b", "#7c3aed")
    markers = ("s", "^", "D", "v")
    for index, csv_path in enumerate(args.comparison_csv):
        with Path(csv_path).open("r", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        label = labels[index] if index < len(labels) else Path(csv_path).parent.name
        datasets.append((label, rows, colors[index % len(colors)], markers[index % len(markers)]))

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.2), sharey=True)
    for ax, side, title in zip(
        axes, ("pressure", "suction"), ("Pressure surface", "Suction surface")
    ):
        first = [row for row in datasets[0][1] if row["side"] == side]
        x = [float(row["surface_distance_pct"]) for row in first]
        nasa = [float(row["nasa_ps_over_pt_ma090"]) for row in first]
        ax.plot(x, nasa, "o-", color="#1f2937", linewidth=1.4, markersize=4.2,
                label="NASA Table VII")
        rmses = []
        for label, rows, color, marker in datasets:
            selected = [row for row in rows if row["side"] == side]
            x_values = [float(row["surface_distance_pct"]) for row in selected]
            cfd = [float(row["cfd_ps_over_pt"]) for row in selected]
            measured = [float(row["nasa_ps_over_pt_ma090"]) for row in selected]
            rmse = math.sqrt(
                sum((a - b) ** 2 for a, b in zip(cfd, measured)) / len(measured)
            )
            rmses.append(f"{label} {rmse:.4f}")
            ax.plot(x_values, cfd, marker + "-", color=color, linewidth=1.4,
                    markersize=3.8, label=label)
        ax.set_title(title + "\nRMSE: " + ", ".join(rmses), fontsize=10)
        ax.set_xlabel("Surface distance from stagnation point (%)")
        ax.grid(True, color="#d1d5db", linewidth=0.6, alpha=0.8)
        ax.set_xlim(0, 100)
        ax.set_ylim(0.35, 1.03)
    axes[0].set_ylabel(r"Static-to-total pressure ratio, $P_s/P_t$")
    axes[0].legend(frameon=False, loc="lower left")
    fig.suptitle("NASA C3X run 44344 aerodynamic validation (Ma2 = 0.89)")
    fig.tight_layout()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
