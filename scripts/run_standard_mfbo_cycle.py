"""Finish startup and execute the first acquisition-driven standard MFBO step."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.storage import ExperimentStore
from bofm.optimization.surrogate import PhysicsInformedPolicy


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/c3x_nasa_standard_mfbo.yaml")
    parser.add_argument("--max-iterations", type=int, default=60)
    parser.add_argument("--bo-iterations", type=int, default=1)
    parser.add_argument(
        "--summary", default="runs/optimization/nasa_standard_mfbo/first_bo_cycle.json"
    )
    args = parser.parse_args()
    if not 1 <= args.max_iterations <= 60:
        parser.error("max-iterations must be between 1 and 60")
    if args.bo_iterations < 1:
        parser.error("bo-iterations must be positive")

    config = load_optimization_config(args.config)
    if bool(config.prior.get("enabled", True)):
        raise RuntimeError("standard MFBO cycle requires physics_prior.enabled=false")
    store = ExperimentStore(config.database)
    if any(item["status"] in {"pending", "running"} for item in store.trials()):
        raise RuntimeError("ledger contains a pending/running trial")

    summary_path = Path(args.summary).resolve()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "running",
        "started_at": now(),
        "config": str(Path(args.config).resolve()),
        "prior_enabled": False,
        "max_iterations": args.max_iterations,
        "requested_bo_iterations": args.bo_iterations,
        "cost_before": store.cost_used(),
        "trials": [],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    bo_completed = 0
    for step in range(1, args.max_iterations + 1):
        trials_before = store.trials()
        proposal = PhysicsInformedPolicy(config).propose(trials_before)
        print("=" * 88, flush=True)
        print(
            f"MFBO step {step}/{args.max_iterations} | proposal={proposal.source} "
            f"fidelity={proposal.fidelity} | cost={store.cost_used():.3f}/{config.budget:.3f}",
            flush=True,
        )
        print("design=" + json.dumps(proposal.design, sort_keys=True), flush=True)
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/run_one_optimization_iteration.py",
                "--config",
                str(Path(args.config).resolve()),
            ],
            cwd=ROOT,
        )
        if completed.returncode:
            summary.update(
                {
                    "status": "failed",
                    "finished_at": now(),
                    "failed_step": step,
                    "returncode": completed.returncode,
                }
            )
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            return completed.returncode

        trial = store.trials()[-1]
        record = {
            "step": step,
            "trial_id": trial["id"],
            "source": trial["source"],
            "fidelity": trial["fidelity"],
            "design": trial["design"],
            "objective": trial["objective"],
            "constraints": trial["constraints"],
            "metrics": trial["metrics"],
            "relative_cost": trial["relative_cost"],
            "run_dir": trial["run_dir"],
            "visuals": str(Path(trial["run_dir"]) / "visuals"),
        }
        summary["trials"].append(record)
        summary["cost_current"] = store.cost_used()
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(
            f"completed trial={trial['id']} objective={float(trial['objective']):.8f} "
            f"source={trial['source']} fidelity={trial['fidelity']}",
            flush=True,
        )
        if trial["source"] == "standard_constrained_ei":
            bo_completed += 1
            if bo_completed >= args.bo_iterations:
                summary.update(
                    {
                        "status": "completed",
                        "finished_at": now(),
                        "bo_iterations_completed": bo_completed,
                        "cost_after": store.cost_used(),
                    }
                )
                summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                print("Requested acquisition-driven MFBO iteration completed.", flush=True)
                return 0

    summary.update(
        {
            "status": "max_iterations_reached",
            "finished_at": now(),
            "bo_iterations_completed": bo_completed,
            "cost_after": store.cost_used(),
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
