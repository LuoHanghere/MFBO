"""Headless optimization runner for smoke tests and compute nodes."""
from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.engine import EngineState, OptimizationEngine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "c3x_optimization.yaml"))
    args = parser.parse_args()
    engine = OptimizationEngine(load_optimization_config(args.config))
    engine.start()
    while engine.state not in {EngineState.COMPLETED, EngineState.ERROR, EngineState.IDLE}:
        snapshot = engine.snapshot()
        print(
            f'\rstate={snapshot["state"]:<9} cost={snapshot["cost_used"]:.2f}/'
            f'{snapshot["budget"]:.2f} current={snapshot["current_trial_id"]}',
            end="",
            flush=True,
        )
        time.sleep(0.5)
    print()
    return 1 if engine.state == EngineState.ERROR else 0


if __name__ == "__main__":
    raise SystemExit(main())
