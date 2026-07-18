"""Charge one accepted cached CFD observation to multiple optimization ledgers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.storage import ExperimentStore
from bofm.optimization.surrogate import PhysicsInformedPolicy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", action="append", required=True)
    parser.add_argument("--design-json", required=True)
    parser.add_argument("--fidelity", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--source", default="shared_cfd_cache")
    parser.add_argument(
        "--allow-out-of-order",
        action="store_true",
        help="Record a declared calibration/audit point even when it is not the policy's next proposal",
    )
    args = parser.parse_args()

    design = json.loads(Path(args.design_json).resolve().read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).resolve().read_text(encoding="utf-8"))
    run_dir = Path(args.run_dir).resolve()
    for config_path in args.config:
        config = load_optimization_config(config_path)
        fidelity = config.fidelity(args.fidelity)
        if fidelity.kind != "cfd":
            raise ValueError(f"shared result must be CFD, got {fidelity.kind}")
        store = ExperimentStore(config.database)
        trials = store.trials()
        if any(
            item["fidelity"] == fidelity.name
            and np.linalg.norm(config.encode(item["design"]) - config.encode(design)) < 1e-10
            for item in trials
        ):
            raise RuntimeError(
                f"duplicate {fidelity.name} design in ledger {config.database}"
            )
        proposal = PhysicsInformedPolicy(config).propose(trials)
        distance = np.linalg.norm(config.encode(proposal.design) - config.encode(design))
        if (proposal.fidelity != fidelity.name or distance >= 1e-10) and not args.allow_out_of_order:
            raise RuntimeError(
                f"cached observation is not the current proposal for {config.name}: "
                f"expected {proposal.fidelity} {proposal.design}, distance={distance:.3g}"
            )
        trial_id = store.create_trial(
            design,
            fidelity.name,
            args.source,
            fidelity.relative_cost,
            proposal.predicted
            if proposal.fidelity == fidelity.name and distance < 1e-10
            else {},
        )
        store.mark_running(trial_id, run_dir)
        store.complete(
            trial_id,
            float(result["objective"]),
            {key: float(value) for key, value in result.get("constraints", {}).items()},
            dict(result.get("metrics", {})),
        )
        store.add_event(
            f"accepted shared CFD result charged at nominal {fidelity.name} cost",
            trial_id=trial_id,
        )
        print(f"{config.name}: recorded trial {trial_id}, cost={store.cost_used():.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
