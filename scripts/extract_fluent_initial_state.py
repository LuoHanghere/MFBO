"""Extract physically useful initialization values from a converged inlet."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--surface", default="inlet")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--cores", type=int, default=8)
    args = ap.parse_args()
    out = Path(args.out_json).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    result: dict = {"surface": args.surface}
    solver = None
    try:
        solver = F.launch(
            mode="solver", processor_count=args.cores, ui_mode="no_gui",
            precision="single",
        )
        solver.settings.file.read_case(file_name=str(Path(args.case).resolve()))
        solver.settings.file.read_data(file_name=str(Path(args.data).resolve()))
        surfaces = solver.fields.field_info.get_surfaces_info()
        meta = surfaces[args.surface]
        ids = [int(value) for value in meta.get("surface_id", [])]
        scalar_info = solver.fields.field_info.get_scalar_fields_info()
        wanted_tokens = (
            "velocity", "pressure", "temperature", "turbulent-kinetic",
            "dissipation", "epsilon", "turbulent-viscosity",
        )
        selected = [
            name for name in scalar_info
            if any(token in name.lower() for token in wanted_tokens)
        ]
        result["available_matching_fields"] = selected
        result["fields"] = {}
        for field_name in selected:
            try:
                data_by_id = solver.fields.field_data.get_scalar_field_data(
                    field_name=field_name, surface_ids=ids, node_value=True
                )
                values = [
                    float(item.scalar_data)
                    for block in data_by_id.values()
                    for item in block.data
                    if math.isfinite(float(item.scalar_data))
                ]
                if values:
                    result["fields"][field_name] = {
                        "count": len(values),
                        "min": min(values),
                        "mean": statistics.fmean(values),
                        "max": max(values),
                    }
            except Exception as exc:
                result["fields"][field_name] = {"error": repr(exc)}
        result["status"] = "ok"
        return 0
    except Exception:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        return 1
    finally:
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        if solver is not None:
            try:
                solver.exit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
