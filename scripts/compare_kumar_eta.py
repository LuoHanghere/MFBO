"""Compare Fluent lateral effectiveness profiles with digitized Kumar curves."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def metrics(sim: pd.DataFrame, ref: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    sim = sim.sort_values("Z_over_D").copy()
    ref = ref.sort_values("Z_over_D").copy()
    lo = max(float(sim.Z_over_D.min()), float(ref.Z_over_D.min()))
    hi = min(float(sim.Z_over_D.max()), float(ref.Z_over_D.max()))
    sim = sim[(sim.Z_over_D >= lo) & (sim.Z_over_D <= hi)].copy()
    if len(sim) < 5:
        raise ValueError(f"Insufficient overlapping CFD samples: {len(sim)}")
    sim["eta_reference"] = np.interp(sim.Z_over_D, ref.Z_over_D, ref.eta)
    sim["eta_error"] = sim.eta - sim.eta_reference
    err = sim.eta_error.to_numpy(float)
    sim_eta = sim.eta.to_numpy(float)
    ref_eta = sim.eta_reference.to_numpy(float)
    corr = float(np.corrcoef(sim_eta, ref_eta)[0, 1]) if len(sim) > 1 else float("nan")
    out = {
        "sample_count": len(sim),
        "overlap_Z_over_D": [lo, hi],
        "eta_mae": float(np.mean(np.abs(err))),
        "eta_rmse": float(np.sqrt(np.mean(err ** 2))),
        "eta_max_abs_error": float(np.max(np.abs(err))),
        "eta_mean_cfd": float(np.mean(sim_eta)),
        "eta_mean_reference": float(np.mean(ref_eta)),
        "eta_mean_bias": float(np.mean(err)),
        "shape_correlation": corr,
        "reference_digitization_eta_uncertainty": 0.015,
    }
    return out, sim


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post-dir", required=True)
    ap.add_argument("--out-json")
    ap.add_argument("--out-plot")
    args = ap.parse_args()
    post = Path(args.post_dir).resolve()
    refs = ROOT / "configs" / "validation"
    cases = {
        "pressure": (
            post / "eta_lateral_ps_xcax_0p31.csv",
            refs / "kumar_fig6_ps_forward_30deg.csv",
        ),
        "suction": (
            post / "eta_lateral_ss_xcax_0p48.csv",
            refs / "kumar_fig7_ss_forward_35deg.csv",
        ),
    }
    result = {
        "definition": "CFD profile compared at CFD bin centers to linearly interpolated digitized reference",
        "acceptance_is_not_automatic": True,
        "sides": {},
    }
    fig, axes = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    for ax, (side, (sim_path, ref_path)) in zip(axes, cases.items()):
        sim = pd.read_csv(sim_path)
        ref = pd.read_csv(ref_path)
        side_metrics, aligned = metrics(sim, ref)
        result["sides"][side] = side_metrics
        ax.plot(ref.Z_over_D, ref.eta, "ko-", ms=3, lw=1, label="Kumar digitization")
        ax.plot(sim.Z_over_D, sim.eta, "r.-", ms=4, lw=1, label="Fluent")
        ax.fill_between(
            ref.Z_over_D.to_numpy(float),
            ref.eta.to_numpy(float) - 0.015,
            ref.eta.to_numpy(float) + 0.015,
            color="k", alpha=0.10, label="digitization +/-0.015",
        )
        ax.set_ylabel("eta")
        ax.set_title(f"{side}: RMSE={side_metrics['eta_rmse']:.4f}, r={side_metrics['shape_correlation']:.3f}")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
        aligned.to_csv(post / f"kumar_{side}_aligned_samples.csv", index=False)
    axes[-1].set_xlabel("Z/D")
    axes[-1].set_xlim(-7.5, 7.5)
    axes[0].set_ylim(0, 1)
    axes[1].set_ylim(0, 1)
    fig.tight_layout()
    out_json = Path(args.out_json).resolve() if args.out_json else post / "kumar_alignment_metrics.json"
    out_plot = Path(args.out_plot).resolve() if args.out_plot else post / "kumar_alignment.png"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    fig.savefig(out_plot, dpi=180)
    plt.close(fig)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
