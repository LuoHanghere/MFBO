"""Inspect Fluent mesh quality without modifying the mesh."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--cores", type=int, default=8)
    ap.add_argument("--precision", choices=("single", "double"), default="single")
    args = ap.parse_args()

    mesh = Path(args.mesh).resolve()
    out = Path(args.out_json).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    session = None
    result: dict = {
        "mesh": str(mesh),
        "cores": args.cores,
        "precision": args.precision,
    }
    try:
        session = F.launch(
            mode="meshing",
            processor_count=args.cores,
            ui_mode="no_gui",
            precision=args.precision,
        )
        session.tui.file.read_mesh(F.tui_path(mesh))
        utilities = session.meshing_utilities
        result["cell_count"] = int(
            utilities.get_cell_zone_count(cell_zone_name_pattern="*")
        )
        result["face_count"] = int(
            utilities.get_face_zone_count(face_zone_name_pattern="*")
        )
        result["cell_quality"] = {}
        for measure in ("Orthogonal Quality", "Skewness"):
            try:
                value = utilities.get_cell_quality_limits(
                    cell_zone_name_pattern="*", measure=measure
                )
                result["cell_quality"][measure] = value
            except Exception as exc:
                result["cell_quality"][measure] = {"error": repr(exc)}
        result["status"] = "ok"
        return 0
    except Exception:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        return 1
    finally:
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        if session is not None:
            try:
                session.exit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
