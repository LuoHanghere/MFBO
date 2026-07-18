"""List boundary zones in a Fluent case (diagnostic)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bofm.cfd.fluent as F

ap = argparse.ArgumentParser()
ap.add_argument("--case", required=True)
ap.add_argument("--cores", type=int, default=1)
args = ap.parse_args()

s = F.launch(mode="solver", processor_count=args.cores, ui_mode="no_gui")
s.tui.file.read_case(str(Path(args.case).resolve()))
bc = s.settings.setup.boundary_conditions
for name in sorted(str(z) for z in bc.keys()):
    print(name, type(bc[name]).__name__ if hasattr(bc[name], '__class__') else "")
s.exit()
