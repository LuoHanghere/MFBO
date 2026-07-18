"""Plot NASA pressure, wall-y+, and effectiveness metrics across mesh tiers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-dir", action="append", required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if len(args.post_dir) != len(args.label):
        parser.error("--post-dir and --label counts must match")

    rows = []
    for label, post_dir in zip(args.label, args.post_dir):
        root = Path(post_dir)
        pressure = json.loads(
            (root / "nasa_surface_pressure_summary.json").read_text(encoding="utf-8")
        )
        yplus = json.loads(
            (root / "wall_yplus_summary.json").read_text(encoding="utf-8")
        )
        bo_summary = json.loads(
            (root / "bo_summary.json").read_text(encoding="utf-8")
        )
        rows.append({
            "label": label,
            "pressure": [
                pressure["rmse"],
                pressure["sides"]["pressure"]["rmse"],
                pressure["sides"]["suction"]["rmse"],
            ],
            "yplus": [yplus["mean"], yplus["p95"], yplus["max"]],
            "eta": [
                bo_summary["objective"]["eta_bar"],
                bo_summary["objective"]["protected_eta_bar"],
            ],
        })

    colors = ["#d1493f", "#2563eb", "#16845b"]
    fig, axes = plt.subplots(1, 3, figsize=(14.0, 4.1))
    width = min(0.24, 0.72 / len(rows))
    for index, row in enumerate(rows):
        offset = (index - (len(rows) - 1) / 2.0) * width
        color = colors[index % len(colors)]
        axes[0].bar(np.arange(3) + offset, row["pressure"], width, label=row["label"], color=color)
        axes[1].bar(np.arange(3) + offset, row["yplus"], width, label=row["label"], color=color)
        axes[2].bar(np.arange(2) + offset, row["eta"], width, label=row["label"], color=color)

    axes[0].set_title("NASA surface-pressure error")
    axes[0].set_xticks(np.arange(3), ["Overall", "Pressure", "Suction"])
    axes[0].set_ylabel(r"RMSE of $P_s/P_t$")
    axes[0].grid(axis="y", color="#d1d5db", linewidth=0.6)
    axes[1].set_title("Vane-wall near-wall resolution")
    axes[1].set_xticks(np.arange(3), ["Mean", "P95", "Maximum"])
    axes[1].set_ylabel(r"Wall $y^+$")
    axes[1].grid(axis="y", color="#d1d5db", linewidth=0.6)
    axes[2].set_title("Adiabatic effectiveness")
    axes[2].set_xticks(np.arange(2), ["Whole wall", "Protected area"])
    axes[2].set_ylabel(r"Area-weighted $\eta$")
    axes[2].set_ylim(0.0, max(max(row["eta"]) for row in rows) * 1.18)
    axes[2].grid(axis="y", color="#d1d5db", linewidth=0.6)
    axes[0].legend(frameon=False)
    fig.suptitle("NASA C3X run 44344 mesh-tier comparison")
    fig.tight_layout()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
