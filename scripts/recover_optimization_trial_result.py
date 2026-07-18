"""Complete an interrupted ledger trial from a subsequently recovered result contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.storage import ExperimentStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--trial-id", type=int, required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    config = load_optimization_config(args.config)
    store = ExperimentStore(config.database)
    matches = [item for item in store.trials() if item["id"] == args.trial_id]
    if len(matches) != 1:
        raise RuntimeError(f"trial {args.trial_id} not found")
    trial = matches[0]
    if trial["status"] not in {"running", "failed"}:
        raise RuntimeError(f"trial status is {trial['status']}, expected running/failed")
    result_path = Path(args.result).resolve()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    store.complete(
        args.trial_id,
        float(result["objective"]),
        {key: float(value) for key, value in result.get("constraints", {}).items()},
        dict(result.get("metrics", {})),
    )
    store.add_event(
        "interrupted infrastructure stage recovered from accepted result contract",
        trial_id=args.trial_id,
    )
    summary_path = (
        config.run_root.parent / f"iteration_{args.trial_id:04d}_summary.json"
    )
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary.update(
            {
                "status": "completed",
                "objective": float(result["objective"]),
                "constraints": dict(result.get("constraints", {})),
                "metrics": dict(result.get("metrics", {})),
                "cost_after": store.cost_used(),
                "result_json": str(result_path),
                "recovered_from_infrastructure_failure": True,
            }
        )
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        f"recovered trial {args.trial_id}: objective={float(result['objective']):.9f}, "
        f"cost={store.cost_used():.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
