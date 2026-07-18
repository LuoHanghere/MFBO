"""Execute exactly one optimization ask-evaluate-record iteration."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.evaluator import build_evaluator
from bofm.optimization.storage import ExperimentStore
from bofm.optimization.surrogate import PhysicsInformedPolicy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--summary",
        help="Machine-readable iteration summary; defaults below the configured run root",
    )
    args = parser.parse_args()

    config = load_optimization_config(args.config)
    store = ExperimentStore(config.database)
    trials = store.trials()
    proposal = PhysicsInformedPolicy(config).propose(trials)
    fidelity = config.fidelity(proposal.fidelity)
    cost_before = store.cost_used()
    if cost_before + fidelity.relative_cost > config.budget + 1e-12:
        raise RuntimeError(
            f"proposal exceeds budget: {cost_before} + {fidelity.relative_cost} > {config.budget}"
        )

    trial_id = store.create_trial(
        proposal.design,
        proposal.fidelity,
        proposal.source,
        fidelity.relative_cost,
        proposal.predicted,
    )
    run_dir = config.run_root / f"trial_{trial_id:04d}_{proposal.fidelity}"
    summary_path = (
        Path(args.summary).resolve()
        if args.summary
        else config.run_root.parent / f"iteration_{trial_id:04d}_summary.json"
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "running",
        "config": str(Path(args.config).resolve()),
        "experiment": config.name,
        "trial_id": trial_id,
        "fidelity": proposal.fidelity,
        "mesh_tier": fidelity.mesh_tier,
        "source": proposal.source,
        "design": proposal.design,
        "predicted": proposal.predicted,
        "relative_cost": fidelity.relative_cost,
        "cost_before": cost_before,
        "run_dir": str(run_dir.resolve()),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    store.mark_running(trial_id, run_dir)
    store.add_event(
        f"single-step trial {trial_id} started ({proposal.source}, {proposal.fidelity})",
        trial_id=trial_id,
    )
    try:
        evaluator = build_evaluator(config)
        result = evaluator.evaluate(
            proposal.design,
            proposal.fidelity,
            run_dir,
            lambda message: store.add_event(message, trial_id=trial_id),
        )
        store.complete(trial_id, result.objective, result.constraints, result.metrics)
        store.add_event(
            f"single-step trial {trial_id} completed: {config.objective_name}={result.objective:.9f}",
            trial_id=trial_id,
        )
        summary.update(
            {
                "status": "completed",
                "objective": result.objective,
                "constraints": result.constraints,
                "metrics": result.metrics,
                "cost_after": store.cost_used(),
                "result_json": str((run_dir / "result.json").resolve()),
            }
        )
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except Exception as exc:
        error = traceback.format_exc()
        store.fail(trial_id, error)
        store.add_event(
            f"single-step trial {trial_id} failed: {exc}", level="error", trial_id=trial_id
        )
        summary.update({"status": "failed", "error": str(exc), "traceback": error})
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
