"""Prepare a no-film C3X validation solver case."""
import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F
from bofm.cfd.nofilm import (
    isentropic_static_pressure,
    load_baseline_config,
    prepare_boundary_zones,
    setup_bcs,
    setup_physics,
    split_merged_boundary,
)
from bofm.cfd.mesh import DomainBounds

root = Path(__file__).resolve().parents[1]
passage = root / "configs" / "c3x_passage.json"
logf = open(root / ".cache_nofilm_setup.txt", "w", encoding="utf-8")

ap = argparse.ArgumentParser()
ap.add_argument("--case-in", default=str(root / "runs" / "fluid" / "c3x_nofilm_L1.cas.h5"))
ap.add_argument("--split-case", default=str(root / "runs" / "fluid" / "c3x_nofilm_split.cas.h5"))
ap.add_argument("--case-out", default=str(root / "runs" / "fluid" / "c3x_nofilm_setup.cas.h5"))
ap.add_argument("--cores", type=int, default=4)
args = ap.parse_args()
case_in = Path(args.case_in)
case_split = Path(args.split_case)
case_out = Path(args.case_out)


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    logf.write(msg + "\n")
    logf.flush()


config = load_baseline_config()
cond = config["conditions"]
pt = float(cond["inlet_total_pressure_kPa"]) * 1000.0
tt = float(cond["inlet_total_temperature_K"])
ma_out = float(cond["exit_mach"])
p_out_guess = isentropic_static_pressure(pt, tt, ma_out)
log("target Pt [Pa]:", pt, "Tt [K]:", tt, "p_out guess [Pa]:", f"{p_out_guess:.0f}")

s = None
try:
    bounds = DomainBounds.from_passage_json(passage, span_mm=3.96)
    s = F.launch(mode="solver", processor_count=args.cores, ui_mode="no_gui")
    log("version:", s.get_fluent_version())
    s.tui.file.read_case(str(case_in))
    log("read case:", case_in)

    split_merged_boundary(s, angle_deg=1.0)
    s.tui.file.write_case(str(case_split))
    log("wrote split case:", case_split, "exists:", case_split.exists())

    summary = prepare_boundary_zones(s, case_split, bounds)
    log("classified counts:",
        {k: len(v) for k, v in summary["classified"].items() if k != "periodic_pairs"})
    log("periodic pairs:", summary["stable"]["periodic_pairs"])

    setup_physics(s)
    log("physics: energy ON, kw-sst, ideal-gas air")
    setup_bcs(s, config)
    log("BCs: pressure inlet/outlet, span symmetry, periodic interfaces, adiabatic walls")

    s.tui.file.write_case(str(case_out))
    log("wrote setup case:", case_out, "exists:", case_out.exists())
    log("DONE_OK")
except Exception:
    log("EXCEPTION:\n" + traceback.format_exc())
finally:
    try:
        if s is not None:
            s.exit()
    except Exception:
        pass
    logf.close()
