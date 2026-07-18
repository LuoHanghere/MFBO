"""Solver-stage split of the single Fluent wall zone by feature angle."""
from __future__ import annotations

import argparse
import traceback
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-in", required=True)
    parser.add_argument("--case-out", required=True)
    parser.add_argument("--wall-zone", default="fluid:1")
    parser.add_argument("--angle-deg", type=float, default=60.0)
    parser.add_argument("--cores", type=int, default=4)
    args = parser.parse_args()
    case_in = Path(args.case_in).resolve()
    case_out = Path(args.case_out).resolve()
    case_out.parent.mkdir(parents=True, exist_ok=True)
    log_path = case_out.with_name(case_out.name.replace(".cas.h5", "_split.log"))
    handle = log_path.open("w", encoding="utf-8")

    def log(*items):
        text = " ".join(str(x) for x in items)
        print(text, flush=True)
        handle.write(text + "\n")
        handle.flush()

    solver = None
    try:
        solver = F.launch(mode="solver", processor_count=args.cores, ui_mode="no_gui")
        log("Fluent:", solver.get_fluent_version())
        solver.tui.file.read_case(str(case_in))
        log("read:", case_in)
        solver.tui.mesh.modify_zones.sep_face_zone_angle(
            args.wall_zone, str(args.angle_deg), "yes"
        )
        log("split:", args.wall_zone, "angle:", args.angle_deg)
        solver.tui.file.write_case(str(case_out))
        log("wrote:", case_out, "exists:", case_out.exists())
        return 0
    except Exception:
        log(traceback.format_exc())
        return 1
    finally:
        try:
            if solver is not None:
                solver.exit()
        except Exception:
            pass
        handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
