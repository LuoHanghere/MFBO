"""Continue a saved film-cooling case/data pair without reinitialization."""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F
from bofm.cfd.workbench_setup import (
    set_solution_limits,
    set_under_relaxation_factors,
    setup_numerics_second_order,
    setup_workbench_outer_bcs,
)
from bofm.cfd.nofilm import load_baseline_config
from bofm.workbench.bc import load_simulation_case


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--additional-iters", type=int, required=True)
    parser.add_argument("--out-prefix", required=True)
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--precision", choices=("single", "double"), default="single")
    parser.add_argument("--keep-first-order", action="store_true")
    parser.add_argument("--energy-urf", type=float)
    parser.add_argument("--momentum-urf", type=float)
    parser.add_argument("--turbulence-urf", type=float)
    parser.add_argument("--temperature-min-k", type=float)
    parser.add_argument("--temperature-max-k", type=float)
    parser.add_argument("--reapply-outer-bcs", action="store_true")
    parser.add_argument("--simulation-case", default="nasa_44344_validation")
    args = parser.parse_args()

    out_prefix = Path(args.out_prefix).resolve()
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_prefix.with_name(out_prefix.name + "_continue.log")
    stream = log_path.open("w", encoding="utf-8")

    def log(*items):
        text = " ".join(str(item) for item in items)
        print(text, flush=True)
        stream.write(text + "\n")
        stream.flush()

    solver = None
    try:
        solver = F.launch(
            mode="solver", processor_count=args.cores, ui_mode="no_gui",
            precision=args.precision,
        )
        log("Fluent:", solver.get_fluent_version(), "cores:", args.cores)
        solver.tui.file.read_case(F.tui_path(Path(args.case).resolve()))
        solver.tui.file.read_data(F.tui_path(Path(args.data).resolve()))
        log("read case/data without initialization")
        if args.reapply_outer_bcs:
            sim_case = load_simulation_case(args.simulation_case)
            bc_summary = setup_workbench_outer_bcs(
                solver, load_baseline_config(), sim_case,
            )
            applied_types = {
                name: spec["type"] for name, spec in bc_summary["bcs_applied"].items()
            }
            log("reapplied outer BCs:", applied_types)
            log("wall thermal mode:", bc_summary.get("wall_thermal_mode"),
                "temperature K:", bc_summary.get("wall_temperature_K"))
        requested_urfs = {}
        if args.energy_urf is not None:
            requested_urfs["energy"] = args.energy_urf
        if args.momentum_urf is not None:
            requested_urfs["momentum"] = args.momentum_urf
        if args.turbulence_urf is not None:
            requested_urfs.update({
                "k": args.turbulence_urf,
                "omega": args.turbulence_urf,
                "epsilon": args.turbulence_urf,
            })
        if requested_urfs:
            applied = set_under_relaxation_factors(solver, requested_urfs)
            log("updated URFs:", applied)
        requested_limits = {}
        if args.temperature_min_k is not None:
            requested_limits["temperature_min"] = args.temperature_min_k
        if args.temperature_max_k is not None:
            requested_limits["temperature_max"] = args.temperature_max_k
        if requested_limits:
            log("updated limits:", set_solution_limits(solver, requested_limits))
        if not args.keep_first_order:
            log("second-order schemes:", setup_numerics_second_order(solver))
        log("additional iterations:", args.additional_iters)
        solver.tui.solve.iterate(str(args.additional_iters))
        case_out = out_prefix.with_suffix(".cas.h5")
        data_out = out_prefix.with_suffix(".dat.h5")
        solver.tui.file.write_case(F.tui_path(case_out))
        solver.tui.file.write_data(F.tui_path(data_out))
        log("wrote:", case_out)
        log("wrote:", data_out)
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
        stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
