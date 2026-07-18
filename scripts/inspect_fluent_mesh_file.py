"""Inspect a Fluent mesh/case file and write basic mesh inventory JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F


def _call(obj: Any, *names: str) -> Any:
    current = obj
    for name in names:
        current = getattr(current, name)
    return current()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--cores", type=int, default=4)
    args = ap.parse_args()

    mesh = Path(args.mesh).resolve()
    out_json = Path(args.out_json).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)

    session = None
    result: dict[str, Any] = {"mesh": str(mesh), "exists": mesh.exists()}
    try:
        session = F.launch(mode="meshing", processor_count=args.cores, ui_mode="no_gui")
        result["fluent_version"] = str(session.get_fluent_version())
        session.tui.file.read_mesh(str(mesh))
        result["cell_count"] = int(session.meshing_utilities.get_cell_zone_count(cell_zone_name_pattern="*"))
        result["face_count"] = int(session.meshing_utilities.get_face_zone_count(face_zone_name_pattern="*"))
        result["boundary_zone_counts"] = {}
        for name in [
            "inlet", "outlet", "qian", "ss", "ps", "vane_wall",
            "film_hole_wall", "periodic_low", "periodic_high", "span_low", "span_high",
        ]:
            try:
                result["boundary_zone_counts"][name] = int(
                    session.meshing_utilities.get_face_zone_count(face_zone_name_pattern=name)
                )
            except Exception as exc:
                result["boundary_zone_counts"][name] = {"error": repr(exc)}
        result["status"] = "ok"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = repr(exc)
        out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 1
    finally:
        try:
            if session is not None:
                session.exit()
        except Exception:
            pass

    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
