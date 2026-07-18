"""Launch the persistent BOFM optimization desktop monitor."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.ui import OptimizationApp


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "c3x_optimization.yaml"))
    args = parser.parse_args()
    app = OptimizationApp(load_optimization_config(args.config))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
