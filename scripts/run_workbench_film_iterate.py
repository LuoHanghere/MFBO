"""Iterate a prepared Workbench film case (10-core default, residuals to terminal)."""
from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F
from bofm.cfd.workbench_setup import (
    set_under_relaxation_factors,
    stabilize_film_startup,
    setup_numerics_second_order,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--case",
        default=str(ROOT / "runs" / "workbench" / "baseline" / "c3x_wb_baseline_setup.cas.h5"),
    )
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--startup-iters", type=int, default=200,
                    help="First-order startup iterations before switching to second order")
    ap.add_argument(
        "--flow-only-startup-iters",
        type=int,
        default=0,
        help="Initial first-order iterations with energy temporarily disabled",
    )
    ap.add_argument(
        "--initial-state-json",
        help="Converged inlet summary from extract_fluent_initial_state.py",
    )
    ap.add_argument("--initial-velocity-scale", type=float, default=1.0)
    ap.add_argument("--initial-pressure-pa", type=float)
    ap.add_argument("--initial-temperature-k", type=float)
    ap.add_argument("--initial-k", type=float)
    ap.add_argument("--initial-epsilon", type=float)
    ap.add_argument("--initialization", choices=("hybrid", "standard"), default="hybrid")
    ap.add_argument(
        "--out-prefix",
        default=str(ROOT / "runs" / "workbench" / "baseline" / "c3x_wb_baseline_run"),
    )
    ap.add_argument("--cores", type=int, default=10)
    ap.add_argument("--precision", choices=("single", "double"), default="single")
    ap.add_argument("--energy-urf", type=float, default=0.8)
    ap.add_argument("--temperature-min-k", type=float, default=100.0)
    ap.add_argument("--temperature-max-k", type=float, default=5000.0)
    args = ap.parse_args()

    log_path = ROOT / ".cache_workbench_film_iterate.txt"
    logf = open(log_path, "w", encoding="utf-8")

    def log(*items):
        msg = " ".join(str(x) for x in items)
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    solver = None
    try:
        case_in = Path(args.case).resolve()
        out_prefix = Path(args.out_prefix).resolve()
        out_prefix.parent.mkdir(parents=True, exist_ok=True)

        solver = F.launch(mode="solver", processor_count=args.cores, ui_mode="no_gui",
                          precision=args.precision)
        log("Fluent:", solver.get_fluent_version(), "cores:", args.cores,
            "precision:", args.precision)
        solver.tui.file.read_case(F.tui_path(case_in))
        log("read case:", case_in)

        startup_iters = min(max(args.startup_iters, 0), args.iters)
        final_iters = args.iters - startup_iters
        log("iterating:", args.iters,
            f"({args.initialization} init, no outlet patch, conservative URF)")
        startup_controls = stabilize_film_startup(
            solver,
            energy_urf=args.energy_urf,
            temperature_min_K=args.temperature_min_k,
            temperature_max_K=args.temperature_max_k,
        )
        log("startup controls:", startup_controls)
        log("initialization:", args.initialization)
        if args.initialization == "hybrid":
            solver.tui.solve.initialize.hyb_initialization()
        else:
            # A bare standard initialization leaves this pressure-based case at
            # zero gauge pressure.  With zero operating pressure Fluent then
            # limits the absolute pressure to 1 Pa in every cell.  Compute the
            # initial field from the mainstream inlet first so pressure,
            # temperature, velocity, and turbulence values are physical.
            log("standard initialization defaults from zone: inlet")
            initialization = solver.settings.solution.initialization
            initialization.initialization_type = "standard"
            log("standard initialization state:", initialization.get_state())
            # Zone names are dynamic child commands below the
            # ``compute-defaults`` TUI menu in Fluent 24.2.
            compute_defaults = solver.tui.solve.initialize.compute_defaults
            children = dir(compute_defaults)
            log("compute-defaults children:", children)
            if "pressure_inlet" not in children:
                raise RuntimeError(
                    "Fluent did not expose pressure_inlet below "
                    "solve/initialize/compute-defaults"
                )
            # The boundary type is the command; the concrete zone is its
            # argument (rather than another dynamic submenu).
            compute_defaults.pressure_inlet("inlet")
            log("standard initialization state after compute-defaults:",
                initialization.get_state())
            if args.initial_state_json:
                initial_doc = json.loads(
                    Path(args.initial_state_json).resolve().read_text(encoding="utf-8")
                )
                fields = initial_doc["fields"]
                pressure = float(fields["pressure"]["mean"])
                temperature = float(fields["temperature"]["mean"])
                ux_source = float(fields["x-velocity"]["mean"])
                uy_source = float(fields["y-velocity"]["mean"])
                uz_source = float(fields["z-velocity"]["mean"])
                speed = math.sqrt(
                    ux_source * ux_source + uy_source * uy_source
                    + uz_source * uz_source
                )
                turbulence_intensity = 0.065
                viscosity_ratio = 10.0
                k_value = 1.5 * (turbulence_intensity * speed) ** 2
                density = pressure / (287.055 * temperature)
                molecular_viscosity = 1.7894e-5
                epsilon_value = (
                    density * 0.09 * k_value * k_value
                    / (molecular_viscosity * viscosity_ratio)
                )
                pressure = args.initial_pressure_pa or pressure
                temperature = args.initial_temperature_k or temperature
                ux = ux_source * args.initial_velocity_scale
                uy = uy_source * args.initial_velocity_scale
                uz = uz_source * args.initial_velocity_scale
                k_value = args.initial_k or k_value
                epsilon_value = args.initial_epsilon or epsilon_value
                manual_defaults = {
                    "pressure": pressure,
                    "temperature": temperature,
                    "x-velocity": ux,
                    "y-velocity": uy,
                    "z-velocity": uz,
                    "k": k_value,
                    "epsilon": epsilon_value,
                }
                initialization.defaults.set_state(manual_defaults)
                log("manual physical initialization defaults:", manual_defaults)
                log("standard initialization state after manual override:",
                    initialization.get_state())
                set_under_relaxation_factors(solver, dict((
                    ("pressure", 0.15),
                    ("density", 0.2),
                    ("momentum", 0.25),
                    ("k", 0.2),
                    ("epsilon", 0.2),
                    ("energy", 0.2),
                )))
            solver.tui.solve.initialize.initialize_flow()
        flow_only_iters = min(
            max(args.flow_only_startup_iters, 0), startup_iters
        )
        thermal_startup_iters = startup_iters - flow_only_iters
        if flow_only_iters:
            # Continuation startup for large hot/cold temperature ratios.  The
            # initialized temperature remains available to the ideal-gas
            # density law while the pressure/velocity/turbulence field settles.
            set_under_relaxation_factors(solver, dict((
                ("pressure", 0.15),
                ("density", 0.2),
                ("momentum", 0.2),
                ("k", 0.2),
                ("epsilon", 0.2),
                ("energy", 0.2),
            )))
            log("flow-only first-order startup iterations:", flow_only_iters)
            solver.settings.setup.models.energy = {"enabled": False}
            solver.tui.solve.iterate(str(flow_only_iters))
            solver.settings.setup.models.energy = {"enabled": True}
            log("energy equation re-enabled")
        if thermal_startup_iters:
            log("full-energy first-order startup iterations:", thermal_startup_iters)
            solver.tui.solve.iterate(str(thermal_startup_iters))
        if final_iters:
            applied = setup_numerics_second_order(solver)
            log("second-order schemes:", applied)
            log("second-order iterations:", final_iters)
            solver.tui.solve.iterate(str(final_iters))

        out_case = out_prefix.with_suffix(".cas.h5")
        out_data = out_prefix.with_suffix(".dat.h5")
        solver.tui.file.write_case(F.tui_path(out_case))
        solver.tui.file.write_data(F.tui_path(out_data))
        log("wrote case:", out_case)
        log("wrote data:", out_data)
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
