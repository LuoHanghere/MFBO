"""Fluent solver setup for Workbench-meshed cases (named zones, no SAT, no split).

Expects a .cas.h5 from Discovery -> Fluent Meshing with face labels intact:
  inlet, outlet, qian, ss, ps, periodic_low, periodic_high, span_low, span_high,
  vane_wall, film_hole_wall, fixed_fluid_domain (cell zone).

Do NOT run split_merged_boundary on these cases.
"""
from __future__ import annotations

from pathlib import Path

from bofm.cfd.nofilm import (
    load_baseline_config,
    setup_bcs,
    setup_physics,
    setup_temperature_dependent_air,
    wall_thermal_state,
)
from bofm.workbench.bc import load_simulation_case, workbench_inlet_bc


WORKBENCH_COOLANT_ZONES = ("qian", "ss", "ps")
WORKBENCH_MAIN_ZONES = ("inlet", "outlet")
WORKBENCH_PERIODIC_ZONES = ("periodic_low", "periodic_high")
WORKBENCH_SPAN_ZONES = ("span_low", "span_high")


def _zone_names(solver) -> set[str]:
    return {str(z) for z in solver.settings.setup.boundary_conditions.keys()}


def _set_zone_type(solver, zone: str, ztype: str) -> None:
    solver.tui.define.boundary_conditions.zone_type(zone, ztype)


def setup_numerics_first_order(solver, sim_case: dict | None = None) -> None:
    """Case-selected pressure coupling plus first-order startup schemes."""
    sim_case = sim_case or load_simulation_case()
    requested_coupling = str(
        sim_case.get("numerics", {}).get("pressure_velocity_coupling", "SIMPLEC")
    ).upper()
    methods = solver.settings.solution.methods
    try:
        state = methods.p_v_coupling.get_state()
        if state.get("flow_scheme") != requested_coupling:
            methods.p_v_coupling.flow_scheme = requested_coupling
    except Exception:
        pass
    disc = methods.discretization_scheme
    first_order = {
        "mom": "first-order-upwind",
        "k": "first-order-upwind",
        "omega": "first-order-upwind",
        "epsilon": "first-order-upwind",
        "temperature": "first-order-upwind",
    }
    for key, scheme in first_order.items():
        try:
            disc[key].set_state(scheme)
        except Exception:
            pass


def setup_numerics_second_order(solver) -> dict[str, str]:
    """Switch transport equations to second order for final validation data."""
    disc = solver.settings.solution.methods.discretization_scheme
    requested = {
        "mom": "second-order-upwind",
        "k": "second-order-upwind",
        "omega": "second-order-upwind",
        "epsilon": "second-order-upwind",
        "temperature": "second-order-upwind",
    }
    applied: dict[str, str] = {}
    for key, scheme in requested.items():
        try:
            disc[key].set_state(scheme)
            applied[key] = scheme
        except Exception:
            continue
    if "mom" not in applied or "temperature" not in applied:
        raise RuntimeError(f"Failed to enable required second-order schemes: {applied}")
    return applied


def setup_case_physics(solver, sim_case: dict | None = None) -> str:
    """Set energy/ideal gas and select SST or Kumar realizable k-epsilon."""
    sim_case = sim_case or load_simulation_case()
    setup_physics(solver)
    setup_temperature_dependent_air(
        solver, sim_case.get("numerics", {}).get("air_properties")
    )
    model = str(sim_case.get("numerics", {}).get("turbulence_model", "sst_k_omega"))
    if model in {"sst_k_omega", "sst-k-omega", "sst"}:
        return "sst_k_omega"
    if model not in {"realizable_k_epsilon", "realizable-k-epsilon"}:
        raise ValueError(f"Unsupported turbulence model in simulation case: {model}")
    try:
        solver.tui.define.models.viscous.ke_realizable("yes")
    except Exception as exc:
        raise RuntimeError("Failed to enable realizable k-epsilon for Kumar case") from exc
    return "realizable_k_epsilon"


def _ensure_pressure_inlet(solver, zone: str, pt_pa: float, tt_k: float, tu: float) -> None:
    _set_zone_type(solver, zone, "pressure-inlet")
    bc = solver.settings.setup.boundary_conditions
    bc.pressure_inlet[zone].set_state({
        "momentum": {
            "gauge_total_pressure": {"option": "value", "value": pt_pa},
            "supersonic_or_initial_gauge_pressure": {"option": "value", "value": pt_pa},
            "direction_specification_method": "Normal to Boundary",
        },
        "thermal": {"total_temperature": {"option": "value", "value": tt_k}},
        "turbulence": {
            "turbulence_specification": "Intensity and Viscosity Ratio",
            "turbulent_intensity": tu,
            "turbulent_viscosity_ratio": 10,
        },
    })


def _ensure_mass_flow_inlet(
    solver, zone: str, mass_flow_rate_kg_s: float, tt_k: float, tu: float,
    supersonic_gauge_pressure_pa: float,
) -> None:
    _set_zone_type(solver, zone, "mass-flow-inlet")
    bc = solver.settings.setup.boundary_conditions
    bc.mass_flow_inlet[zone].set_state({
        "momentum": {
            "mass_flow_specification": "Mass Flow Rate",
            "mass_flow_rate": {"option": "value", "value": mass_flow_rate_kg_s},
            "supersonic_gauge_pressure": {
                "option": "value", "value": supersonic_gauge_pressure_pa,
            },
            "direction_specification": "Normal to Boundary",
        },
        "thermal": {"total_temperature": {"option": "value", "value": tt_k}},
        "turbulence": {
            "turbulence_specification": "Intensity and Viscosity Ratio",
            "turbulent_intensity": tu,
            "turbulent_viscosity_ratio": 10,
        },
    })


def _ensure_pressure_outlet(solver, zone: str, p_pa: float, tt_k: float, tu: float) -> None:
    _set_zone_type(solver, zone, "pressure-outlet")
    bc = solver.settings.setup.boundary_conditions
    bc.pressure_outlet[zone].set_state({
        "momentum": {
            "gauge_pressure": {"option": "value", "value": p_pa},
            "backflow_dir_spec_method": "Normal to Boundary",
        },
        "thermal": {"backflow_total_temperature": {"option": "value", "value": tt_k}},
        "turbulence": {
            "turbulence_specification": "Intensity and Viscosity Ratio",
            "backflow_turbulent_intensity": tu,
            "backflow_turbulent_viscosity_ratio": 10,
        },
    })


def _create_translational_periodic(solver, low: str, high: str, translation: list[float],
                                 interface_name: str) -> None:
    solver.settings.mesh.modify_zones.create_periodic_interface(
        periodic_method="non-conformal",
        interface_name=interface_name,
        zone_name=low,
        shadow_zone_name=high,
        rotate_periodic=False,
        new_axis=False,
        origin=[0.0, 0.0, 0.0],
        new_direction=False,
        direction=[0.0, 1.0, 0.0],
        auto_angle=True,
        rotation_angle=0.0,
        auto_translation=False,
        translation=list(translation),
        create_periodic=True,
        auto_offset=False,
        nonconformal_angle=0.0,
        nonconformal_translation=list(translation),
        # Periodic planes geometrically overlap but their independently
        # generated surface triangulations need not be one-to-one.  Fluent
        # recommends the matching option for periodic non-conformal interfaces;
        # disabling it can leave non-overlap wall fragments and has produced
        # interface-penetration warnings on the paper mesh.
        create_matching=True,
        nonconformal_create_periodic=True,
    )
    created_names = _zone_names(solver)
    if interface_name not in created_names and not any(
        name.startswith(interface_name) for name in created_names
    ):
        raise RuntimeError(
            f"Fluent did not create periodic interface {interface_name!r}; "
            f"zones after command={created_names}"
        )


def setup_workbench_outer_bcs(solver, config: dict | None = None,
                              sim_case: dict | None = None) -> dict:
    """Apply NASA-aligned BCs on pre-named Workbench zones (no geometry split)."""
    config = config or load_baseline_config()
    sim_case = sim_case or load_simulation_case()
    names = _zone_names(solver)
    bcs = workbench_inlet_bc(sim_case)
    ms = sim_case["mainstream"]
    tu = float(ms.get("inlet_turbulence_intensity_pct", 6.5)) / 100.0
    tt = float(ms["inlet_total_temperature_K"])

    missing = [z for z in WORKBENCH_MAIN_ZONES + WORKBENCH_COOLANT_ZONES if z not in names]
    if missing:
        raise RuntimeError(
            "Workbench case is missing named zones: %s. "
            "Mesh must come from Discovery -> Fluent Meshing (UseBodyLabels=Yes), "
            "not from SAT/PyFluent headless meshing." % ", ".join(missing)
        )

    _ensure_pressure_inlet(solver, "inlet", bcs["inlet"]["gauge_total_pressure_Pa"], tt, tu)
    _ensure_pressure_outlet(solver, "outlet", bcs["outlet"]["gauge_pressure_Pa"], tt, tu)
    for z in WORKBENCH_COOLANT_ZONES:
        if bcs[z]["type"] == "mass-flow-inlet":
            _ensure_mass_flow_inlet(
                solver, z, bcs[z]["mass_flow_rate_kg_s"],
                bcs[z]["total_temperature_K"], tu,
                bcs[z]["gauge_total_pressure_Pa"],
            )
        else:
            _ensure_pressure_inlet(
                solver, z, bcs[z]["gauge_total_pressure_Pa"],
                bcs[z]["total_temperature_K"], tu,
            )

    wall_doc = sim_case.get("walls", {})
    wall_mode = wall_doc.get(
        "thermal_mode", wall_doc.get("optimization_mode", "adiabatic")
    )
    thermal = wall_thermal_state(
        config,
        wall_thermal=wall_mode,
        wall_temperature_K=wall_doc.get("temperature_K"),
    )
    bc = solver.settings.setup.boundary_conditions
    for wall_name in list(bc.wall.keys()):
        bc.wall[wall_name].set_state({
            "momentum": {"wall_motion": "Stationary Wall", "shear_condition": "No Slip"},
            "thermal": thermal,
        })

    return {
        "zones_found": sorted(names),
        "bcs_applied": bcs,
        "wall_thermal_mode": wall_mode,
        "wall_temperature_K": wall_doc.get("temperature_K"),
    }


def setup_workbench_periodics(solver, *, pitch_mm: float = 117.73,
                            translation_xy_mm: tuple[float, float] | None = None,
                            span_mm: float | None = 14.85,
                            span_mode: str = "periodic") -> list[str]:
    """Create pitchwise (and optionally spanwise) translational periodics if needed."""
    from bofm.cfd.mesh import GEOMETRY_TO_SI

    names = _zone_names(solver)
    actions = []

    if "periodic_periodic_low_periodic_high" in names:
        actions.append("pitch periodic already coupled (periodic_periodic_low_periodic_high)")
    elif WORKBENCH_PERIODIC_ZONES[0] in names and WORKBENCH_PERIODIC_ZONES[1] in names:
        low, high = WORKBENCH_PERIODIC_ZONES
        translation_xy_mm = translation_xy_mm or (0.0, pitch_mm)
        dx_m = float(translation_xy_mm[0]) * GEOMETRY_TO_SI
        dy_m = float(translation_xy_mm[1]) * GEOMETRY_TO_SI
        _create_translational_periodic(
            solver, low, high, [dx_m, dy_m, 0.0], "pitch_periodic_interface",
        )
        actions.append(f"created pitch periodic {low}<->{high} dx={dx_m} m dy={dy_m} m")

    if span_mode == "periodic" and span_mm is not None:
        if all(z in names for z in WORKBENCH_SPAN_ZONES):
            if "span_periodic_interface" not in names and not any(
                n.startswith("span_periodic") for n in names
            ):
                span_m = float(span_mm) * GEOMETRY_TO_SI
                try:
                    _create_translational_periodic(
                        solver, "span_low", "span_high", [0.0, 0.0, span_m],
                        "span_periodic_interface",
                    )
                    actions.append(f"created span periodic span_low<->span_high dz={span_m} m")
                except Exception as exc:
                    actions.append(f"span periodic skipped: {exc}")
            else:
                actions.append("span periodic already present")

    if any("created" in action for action in actions):
        solver.settings.setup.mesh_interfaces.remove_left_handed_interface_faces(
            enable=True,
            update=True,
        )
        actions.append("removed left-handed faces and updated mesh interfaces")

    return actions


def set_under_relaxation_factors(solver, values: dict[str, float]) -> dict[str, float]:
    """Set URFs using the Fluent 24.2 settings keys, returning applied values."""
    aliases = {
        "body_forces": "body-force",
        "momentum": "mom",
        "energy": "temperature",
    }
    urf = solver.settings.solution.controls.under_relaxation
    state = urf.get_state()
    applied: dict[str, float] = {}
    for requested, value in values.items():
        key = aliases.get(requested, requested)
        if key in state:
            state[key] = float(value)
            applied[key] = float(value)
    urf.set_state(state)
    return applied


def set_solution_limits(solver, values: dict[str, float]) -> dict[str, float]:
    """Set solution limits using Fluent 24.2's exact settings names."""
    aliases = {
        "temperature_min": "min_temperature",
        "temperature_max": "max_temperature",
        "turb_viscosity_ratio_max": "max_turb_visc_ratio",
    }
    limits = solver.settings.solution.controls.limits
    state = limits.get_state()
    applied: dict[str, float] = {}
    for requested, value in values.items():
        key = aliases.get(requested, requested)
        if key in state:
            state[key] = float(value)
            applied[key] = float(value)
    limits.set_state(state)
    return applied


def stabilize_film_startup(solver, *, energy_urf: float = 0.8,
                           temperature_min_K: float = 100.0,
                           temperature_max_K: float = 5000.0) -> dict[str, dict[str, float]]:
    """Conservative URF/limits for film-cooled cold-start on Workbench meshes."""
    applied = set_under_relaxation_factors(solver, {
        "pressure": 0.3,
        "density": 0.5,
        "body_forces": 0.5,
        "momentum": 0.5,
        "k": 0.4,
        "omega": 0.4,
        "epsilon": 0.4,
        "energy": float(energy_urf),
    })
    applied_limits = set_solution_limits(solver, {
        "turb_viscosity_ratio_max": 1.0e5,
        "temperature_min": temperature_min_K,
        "temperature_max": temperature_max_K,
    })
    return {"under_relaxation": applied, "limits": applied_limits}


def initialize_workbench_film(solver, n_iter: int = 200) -> None:
    """Hybrid init without outlet velocity patch (avoids fighting coolant inlets)."""
    stabilize_film_startup(solver)
    solver.tui.solve.initialize.hyb_initialization()
    solver.tui.solve.iterate(str(n_iter))


def setup_workbench_film_case(solver, case_path: str | Path,
                              config: dict | None = None,
                              sim_case: dict | None = None,
                              *, span_mm: float = 14.85,
                              pitch_mm: float = 117.73,
                              translation_xy_mm: tuple[float, float] | None = None) -> dict:
    """Read Workbench .cas.h5, set physics/BCs/periodics — no split, no SAT."""
    config = config or load_baseline_config()
    from bofm.cfd.fluent import tui_path

    solver.tui.file.read_case(tui_path(Path(case_path).resolve()))
    return setup_loaded_workbench_film_case(
        solver, config, sim_case=sim_case, span_mm=span_mm, pitch_mm=pitch_mm,
        translation_xy_mm=translation_xy_mm,
    )


def setup_loaded_workbench_film_case(solver,
                                     config: dict | None = None,
                                     sim_case: dict | None = None,
                                     *, span_mm: float = 14.85,
                                     pitch_mm: float = 117.73,
                                     translation_xy_mm: tuple[float, float] | None = None) -> dict:
    """Set physics/BCs/periodics on an already-loaded Workbench case or mesh."""
    config = config or load_baseline_config()
    sim_case = sim_case or load_simulation_case()
    turbulence_model = setup_case_physics(solver, sim_case)
    setup_numerics_first_order(solver, sim_case)
    outer = setup_workbench_outer_bcs(solver, config, sim_case)
    periodics = setup_workbench_periodics(
        solver, pitch_mm=pitch_mm, translation_xy_mm=translation_xy_mm,
        span_mm=span_mm, span_mode="periodic",
    )
    return {
        "outer": outer,
        "periodics": periodics,
        "turbulence_model": turbulence_model,
        "air_properties": str(
            sim_case.get("numerics", {}).get("air_properties", "fluent_constant")
        ),
        "pressure_velocity_coupling": str(
            sim_case.get("numerics", {}).get("pressure_velocity_coupling", "SIMPLEC")
        ).upper(),
    }
