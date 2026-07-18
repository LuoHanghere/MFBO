"""Import an accepted historical result into a new optimization ledger."""
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
    parser.add_argument("--result", required=True)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    config = load_optimization_config(args.config)
    store = ExperimentStore(config.database)
    if store.trials():
        raise RuntimeError(f"refusing to seed non-empty ledger: {config.database}")
    result = json.loads(Path(args.result).resolve().read_text(encoding="utf-8"))
    fidelity = config.fidelities[-1]
    trial_id = store.create_trial(
        config.baseline, fidelity.name, "imported_baseline", fidelity.relative_cost
    )
    store.mark_running(trial_id, Path(args.run_dir).resolve())
    store.complete(
        trial_id,
        float(result["objective"]),
        {key: float(value) for key, value in result["constraints"].items()},
        dict(result.get("metrics", {})),
    )
    store.add_event("accepted periodic-v2 coarse baseline imported", trial_id=trial_id)
    print("seeded trial", trial_id, "in", config.database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
