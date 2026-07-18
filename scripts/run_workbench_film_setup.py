"""Setup a Workbench-meshed film case (named zones, no SAT, no split)."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F
from bofm.cfd.nofilm import load_baseline_config
from bofm.cfd.workbench_setup import setup_loaded_workbench_film_case, setup_workbench_film_case
from bofm.workbench.bc import load_simulation_case

ROOT = Path(__file__).resolve().parents[1]
logf = open(ROOT / ".cache_workbench_film_setup.txt", "w", encoding="utf-8")

ap = argparse.ArgumentParser()
ap.add_argument(
    "--case-in",
    default=str(ROOT / "1_files" / "dp0" / "FLTG" / "Fluent" / "FLTG-2.cas.h5"),
    help="Fluent case from Workbench Fluent Meshing (named boundaries intact)",
)
ap.add_argument(
    "--case-out",
    default=str(ROOT / "runs" / "workbench" / "baseline" / "c3x_wb_baseline_setup.cas.h5"),
)
ap.add_argument("--span-mm", type=float, default=14.85)
ap.add_argument("--pitch-mm", type=float)
ap.add_argument("--cores", type=int, default=10)
ap.add_argument("--precision", choices=("single", "double"), default="single")
ap.add_argument("--simulation-case", default="nasa_44344_validation")
args = ap.parse_args()


def default_periodic_translation_xy_mm() -> tuple[float, float]:
    path = ROOT / "configs" / "c3x_kumar_paper_external_flow.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        translation = data.get("periodic_translation_xy_mm")
        if translation is not None and len(translation) == 2:
            return float(translation[0]), float(translation[1])
        return 0.0, float(data.get("physical_pitch_mm", data.get("pitch_mm", 117.73)))
    except Exception:
        return 0.0, 117.73


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    logf.write(msg + "\n")
    logf.flush()


config = load_baseline_config()
sim_case = load_simulation_case(args.simulation_case)
periodic_translation_xy_mm = default_periodic_translation_xy_mm()
if args.pitch_mm is not None:
    periodic_translation_xy_mm = (0.0, args.pitch_mm)
pitch_mm = periodic_translation_xy_mm[1]
case_in = Path(args.case_in)
case_out = Path(args.case_out)
case_out.parent.mkdir(parents=True, exist_ok=True)
# Fluent's TUI write command does not overwrite an existing HDF5 case in
# headless mode; it can leave the stale file in place while the API call still
# returns.  Remove only the explicitly requested output before launching so a
# successful setup always corresponds to the current input mesh.
if case_out.is_file():
    case_out.unlink()

s = None
try:
    s = F.launch(mode="solver", processor_count=args.cores, ui_mode="no_gui",
                 precision=args.precision)
    log("Fluent:", s.get_fluent_version(), "cores:", args.cores, "precision:", args.precision)
    log("read:", case_in)
    log("periodic translation [dx, dy] mm:", periodic_translation_xy_mm)
    if case_in.name.endswith(".msh.h5"):
        s.settings.file.read_mesh(file_name=str(case_in.resolve()))
        summary = setup_loaded_workbench_film_case(
            s, config, sim_case=sim_case, span_mm=args.span_mm, pitch_mm=pitch_mm,
            translation_xy_mm=periodic_translation_xy_mm,
        )
    else:
        summary = setup_workbench_film_case(
            s, case_in, config, sim_case=sim_case,
            span_mm=args.span_mm, pitch_mm=pitch_mm,
            translation_xy_mm=periodic_translation_xy_mm,
        )
    log("zones:", summary["outer"]["zones_found"])
    log("periodics:", summary["periodics"])
    log("simulation case:", args.simulation_case)
    log("wall thermal mode:", summary["outer"].get("wall_thermal_mode"),
        "temperature K:", summary["outer"].get("wall_temperature_K"))
    log("turbulence:", summary["turbulence_model"])
    log("air properties:", summary["air_properties"])
    log("numerics:", summary["pressure_velocity_coupling"], "+ first-order")
    s.tui.file.write_case(F.tui_path(case_out))
    log("wrote:", case_out, "exists:", case_out.exists())
    log("DONE_OK")
except Exception:
    log("EXCEPTION:\n" + traceback.format_exc())
    raise SystemExit(1)
finally:
    try:
        if s is not None:
            s.exit()
    except Exception:
        pass
    logf.close()
