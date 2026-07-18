"""Summarize and plot thermal convergence checkpoints for NASA C3X runs."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        action="append",
        nargs=3,
        metavar=("TIER", "ITERATION", "POST_DIR"),
        required=True,
    )
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-plot", required=True)
    args = parser.parse_args()

    rows = []
    for tier, iteration_text, post_dir_text in args.checkpoint:
        post_dir = Path(post_dir_text)
        summary = json.loads((post_dir / "bo_summary.json").read_text(encoding="utf-8"))
        rows.append(
            {
                "tier": tier,
                "iteration": int(iteration_text),
                "eta_bar": summary["objective"]["eta_bar"],
                "protected_eta_bar": summary["objective"]["protected_eta_bar"],
                "continuity": summary["diagnostics"]["convergence"]["last_residual_row"]["continuity"],
                "energy": summary["diagnostics"]["convergence"]["last_residual_row"]["energy"],
                "post_dir": str(post_dir.resolve()),
            }
        )
    tier_order = {"coarse": 0, "paper": 1, "fine": 2}
    rows.sort(key=lambda row: (tier_order.get(row["tier"], 99), row["iteration"]))

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    colors = {"coarse": "#d1493f", "paper": "#2563eb", "fine": "#16845b"}
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.9))
    for tier in dict.fromkeys(row["tier"] for row in rows):
        tier_rows = [row for row in rows if row["tier"] == tier]
        iterations = [row["iteration"] for row in tier_rows]
        color = colors.get(tier)
        axes[0].plot(iterations, [row["eta_bar"] for row in tier_rows], "o-", label=tier, color=color)
        axes[1].plot(iterations, [row["protected_eta_bar"] for row in tier_rows], "o-", label=tier, color=color)
    axes[0].set_title("Whole-wall effectiveness")
    axes[1].set_title("Protected-area effectiveness")
    for axis in axes:
        axis.set_xlabel("Solver iteration")
        axis.set_ylabel(r"Area-weighted $\eta$")
        axis.grid(color="#d1d5db", linewidth=0.6)
    axes[0].legend(frameon=False)
    fig.suptitle("NASA C3X run 44344 thermal convergence checkpoints")
    fig.tight_layout()
    output_plot = Path(args.output_plot)
    output_plot.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_plot, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote:", output_csv)
    print("wrote:", output_plot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
