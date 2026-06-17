"""Export no-film Fluent results for ParaView and summarize wall y+."""
import argparse
import csv
import json
import statistics
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F

DEFAULT_FIELDS = [
    "pressure",
    "absolute-pressure",
    "temperature",
    "total-temperature",
    "velocity-magnitude",
    "mach-number",
    "y-plus",
    "wall-shear",
    "heat-transfer-coef-wall-adj",
]


def _surface_ids(meta: dict) -> list[int]:
    ids = meta.get("surface_id", [])
    return [int(i) for i in ids]


def wall_surfaces(solver) -> dict[str, dict]:
    """Return Fluent surfaces whose zone type is wall."""
    surfaces = solver.fields.field_info.get_surfaces_info()
    return {
        name: meta for name, meta in surfaces.items()
        if meta.get("zone_type") == "wall"
    }


def available_fields(solver, requested: list[str]) -> list[str]:
    scalars = solver.fields.field_info.get_scalar_fields_info()
    return [name for name in requested if name in scalars]


def scalar_values(field_data) -> list[float]:
    return [float(item.scalar_data) for item in field_data.data]


def yplus_summary(solver, walls: dict[str, dict]) -> dict:
    """Collect nodal y+ values on all wall surfaces and summarize them."""
    field_data = solver.fields.field_data
    rows = []
    all_values = []
    for name, meta in sorted(walls.items()):
        ids = _surface_ids(meta)
        if not ids:
            continue
        data_by_id = field_data.get_scalar_field_data(
            field_name="y-plus",
            surface_ids=ids,
            node_value=True,
        )
        values = []
        for sid, values_for_id in data_by_id.items():
            vals = scalar_values(values_for_id)
            values.extend(vals)
            all_values.extend(vals)
            if vals:
                rows.append({
                    "surface": name,
                    "surface_id": sid,
                    "count": len(vals),
                    "min": min(vals),
                    "mean": statistics.fmean(vals),
                    "max": max(vals),
                })

    if not all_values:
        raise RuntimeError("No y-plus values were returned for wall surfaces")
    all_values_sorted = sorted(all_values)
    n = len(all_values_sorted)
    p95 = all_values_sorted[min(n - 1, int(0.95 * (n - 1)))]
    return {
        "field": "y-plus",
        "location": "wall surfaces",
        "surface_count": len(walls),
        "sample_count": n,
        "min": min(all_values_sorted),
        "mean": statistics.fmean(all_values_sorted),
        "max": max(all_values_sorted),
        "p95": p95,
        "surfaces": rows,
    }


def export_ensight(solver, out_base: Path, fields: list[str]) -> None:
    """Write an EnSight Gold export that ParaView can open."""
    out_base.parent.mkdir(parents=True, exist_ok=True)
    cellzones = sorted(str(name) for name in solver.settings.setup.cell_zone_conditions.fluid.keys())
    surfaces = sorted(solver.fields.field_info.get_surfaces_info().keys())
    solver.settings.file.export.ensight_gold(
        file_name=str(out_base),
        cell_func_domain_export=fields,
        binary_format=False,
        cellzones=cellzones,
        interior_zone_surfaces=surfaces,
        cell_centered=False,
    )


def write_yplus_files(summary: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "wall_yplus_summary.json"
    csv_path = out_dir / "wall_yplus_surfaces.csv"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["surface", "surface_id", "count", "min", "mean", "max"]
        )
        writer.writeheader()
        writer.writerows(summary["surfaces"])
    return json_path, csv_path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=str(root / "runs" / "fluid" / "c3x_nofilm_refined_run200.cas.h5"))
    ap.add_argument("--data", default=str(root / "runs" / "fluid" / "c3x_nofilm_refined_run200.dat.h5"))
    ap.add_argument("--out-dir", default=str(root / "runs" / "fluid" / "paraview" / "c3x_nofilm_refined_run200"))
    ap.add_argument("--name", default="c3x_nofilm_refined_run200")
    ap.add_argument("--cores", type=int, default=2)
    ap.add_argument("--fields", nargs="*", default=DEFAULT_FIELDS)
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    log_path = root / ".cache_nofilm_export.txt"
    logf = open(log_path, "w", encoding="utf-8")

    def log(*items):
        msg = " ".join(str(x) for x in items)
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    solver = None
    try:
        solver = F.launch(mode="solver", processor_count=args.cores, ui_mode="no_gui")
        log("version:", solver.get_fluent_version())
        solver.tui.file.read_case(str(Path(args.case).resolve()))
        solver.tui.file.read_data(str(Path(args.data).resolve()))
        log("read case/data")

        walls = wall_surfaces(solver)
        log("wall surfaces:", len(walls))
        summary = yplus_summary(solver, walls)
        json_path, csv_path = write_yplus_files(summary, out_dir)
        log("yplus min/mean/p95/max:",
            summary["min"], summary["mean"], summary["p95"], summary["max"])
        log("wrote:", json_path)
        log("wrote:", csv_path)

        fields = available_fields(solver, args.fields)
        out_base = out_dir / args.name
        export_ensight(solver, out_base, fields)
        log("ensight fields:", fields)
        log("ensight base:", out_base)
        log("DONE_OK")
        return 0
    except Exception:
        log("EXCEPTION:\n" + traceback.format_exc())
        return 1
    finally:
        try:
            if solver is not None:
                solver.exit()
        except Exception:
            pass
        logf.close()


if __name__ == "__main__":
    raise SystemExit(main())
