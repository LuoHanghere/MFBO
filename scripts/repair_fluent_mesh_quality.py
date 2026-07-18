"""Improve a loaded Fluent volume mesh and write a separate repaired mesh."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F


def quality_limits(session, measure: str):
    return session.meshing_utilities.get_cell_quality_limits(
        cell_zone_name_pattern="*", measure=measure
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--out-mesh", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--quality-limit", type=float, default=0.05)
    ap.add_argument("--cores", type=int, default=8)
    ap.add_argument("--precision", choices=("single", "double"), default="single")
    args = ap.parse_args()

    mesh = Path(args.mesh).resolve()
    out_mesh = Path(args.out_mesh).resolve()
    out_json = Path(args.out_json).resolve()
    out_mesh.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    session = None
    result: dict = {
        "mesh_in": str(mesh),
        "mesh_out": str(out_mesh),
        "quality_limit": args.quality_limit,
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
        result["cell_count"] = int(
            session.meshing_utilities.get_cell_zone_count(cell_zone_name_pattern="*")
        )
        result["before"] = {
            "Orthogonal Quality": quality_limits(session, "Orthogonal Quality"),
            "Skewness": quality_limits(session, "Skewness"),
        }
        result["improve_return"] = session.meshing.ImproveVolumeMesh(
            QualityMethod="Orthogonal Quality",
            CellQualityLimit=args.quality_limit,
            VMImprovePreferences={},
        )
        result["after"] = {
            "Orthogonal Quality": quality_limits(session, "Orthogonal Quality"),
            "Skewness": quality_limits(session, "Skewness"),
        }
        session.tui.file.write_mesh(F.tui_path(out_mesh))
        result["mesh_out_exists"] = out_mesh.is_file()
        result["mesh_out_bytes"] = out_mesh.stat().st_size if out_mesh.is_file() else 0
        result["status"] = "ok"
        return 0
    except Exception:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        return 1
    finally:
        out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        if session is not None:
            try:
                session.exit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
