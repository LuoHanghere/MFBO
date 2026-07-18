"""Seed accepted NASA L1/L2/L3 baseline observations into an empty ledger."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.prior import FilmCoolingPrior
from bofm.optimization.storage import ExperimentStore


RESULTS = {
    "coarse": (
        ROOT / "runs/optimization/nasa_baselines/coarse_result.json",
        ROOT / "runs/nasa_44344/coarse/post_mdot_iter1800",
    ),
    "paper": (
        ROOT / "runs/optimization/nasa_baselines/paper_result.json",
        ROOT / "runs/nasa_44344/paper/post_iter2500",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = load_optimization_config(args.config)
    store = ExperimentStore(config.database)
    if store.trials():
        raise RuntimeError(f"refusing to seed non-empty ledger: {config.database}")

    for fidelity in config.fidelities:
        if fidelity.kind == "knowledge":
            objective = FilmCoolingPrior(config.prior)(config.baseline)
            constraints = {}
            metrics = {
                "physics_prior": objective,
                "information_kind": "knowledge",
                "imported_baseline": True,
            }
            run_dir = config.run_root / "accepted_baseline_L1"
        else:
            if fidelity.mesh_tier not in RESULTS:
                raise ValueError(f"no accepted NASA result for {fidelity.mesh_tier}")
            result_path, run_dir = RESULTS[fidelity.mesh_tier]
            result = json.loads(result_path.read_text(encoding="utf-8"))
            objective = float(result["objective"])
            constraints = {
                key: float(value) for key, value in result.get("constraints", {}).items()
            }
            metrics = dict(result.get("metrics", {}))
            metrics["imported_baseline"] = True
        trial_id = store.create_trial(
            config.baseline,
            fidelity.name,
            "accepted_nasa_baseline",
            fidelity.relative_cost,
        )
        store.mark_running(trial_id, run_dir)
        store.complete(trial_id, objective, constraints, metrics)
        store.add_event(
            f"accepted NASA baseline imported for {fidelity.name} ({fidelity.mesh_tier})",
            trial_id=trial_id,
        )
        print(f"seeded {fidelity.name}: objective={objective:.9f}")
    print(f"ledger: {config.database}")
    print(f"equivalent high-fidelity cost: {store.cost_used():.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
