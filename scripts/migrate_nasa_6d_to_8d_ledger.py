"""Migrate completed 6D NASA CFD observations into a fresh 8D ledger."""
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
    parser.add_argument(
        "--source-config", default="configs/c3x_nasa_standard_mfbo.yaml"
    )
    parser.add_argument(
        "--target-config", default="configs/c3x_nasa_standard_mfbo_8d.yaml"
    )
    parser.add_argument(
        "--manifest",
        default="runs/optimization/nasa_standard_mfbo_8d/migration_manifest.json",
    )
    args = parser.parse_args()

    source_config = load_optimization_config(args.source_config)
    target_config = load_optimization_config(args.target_config)
    source = ExperimentStore(source_config.database)
    target = ExperimentStore(target_config.database)
    if target.trials():
        raise RuntimeError(f"refusing to migrate into non-empty ledger: {target.path}")

    target_fidelities = {
        item.name: item for item in target_config.fidelities if item.kind == "cfd"
    }
    migrated = []
    for trial in source.trials(("completed",)):
        if trial["fidelity"] not in target_fidelities:
            continue
        design = dict(target_config.baseline)
        design.update(
            {
                name: trial["design"][name]
                for name in trial["design"]
                if name in design
            }
        )
        design = target_config.decode(target_config.encode(design))
        fidelity = target_fidelities[trial["fidelity"]]
        trial_id = target.create_trial(
            design,
            fidelity.name,
            f"migrated_6d:{trial['source']}",
            fidelity.relative_cost,
            trial.get("predicted", {}),
        )
        target.mark_running(trial_id, trial["run_dir"])
        metrics = dict(trial.get("metrics", {}))
        metrics.update(
            {
                "migrated_from_6d_trial": trial["id"],
                "diameter_mm": design["diameter_mm"],
                "span_count": design["span_count"],
            }
        )
        target.complete(
            trial_id,
            float(trial["objective"]),
            {key: float(value) for key, value in trial.get("constraints", {}).items()},
            metrics,
        )
        target.add_event(
            f"migrated completed 6D trial {trial['id']} as 8D anchor",
            trial_id=trial_id,
        )
        migrated.append(
            {
                "source_trial_id": trial["id"],
                "target_trial_id": trial_id,
                "fidelity": fidelity.name,
                "objective": trial["objective"],
                "design": design,
            }
        )

    source_cost = source.cost_used()
    target_cost = target.cost_used()
    target.set_metadata("migration", {
        "source_database": str(source.path),
        "source_equivalent_high_fidelity_cost": source_cost,
        "migrated_equivalent_high_fidelity_cost": target_cost,
        "migrated_trial_count": len(migrated),
        "fixed_new_dimensions": {"diameter_mm": 0.99, "span_count": 5},
    })
    manifest = Path(args.manifest).resolve()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "source_config": str(Path(args.source_config).resolve()),
                "target_config": str(Path(args.target_config).resolve()),
                "source_cost": source_cost,
                "target_cost": target_cost,
                "migrated": migrated,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"migrated {len(migrated)} completed CFD trials")
    print(f"target cost: {target_cost:.3f}")
    print(f"manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
