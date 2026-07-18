"""No-film C3X cascade RANS setup for CR-168015 validation.

Mesh note: the watertight .sat import stores mm-magnitude coordinates but Fluent
reads ACIS numbers as metres. Scale the grid by mesh.GEOMETRY_TO_SI (0.001)
before setting BCs so pitch/span/chord are physically correct.

BC layout (from build_fluid_domain + mesh.tag_zones):
  inlet / outlet          : cascade in/out planes
  periodic_low / high     : translational pitchwise periodicity (+pitch in y)
  span_low / span_high    : symmetry (thin midspan slice, no-film 2D-like case)
  vane_wall               : no-slip wall; thermal condition is switchable
                            (adiabatic for the BO loop / eta objective,
                            isothermal for CR-168015 heat-transfer validation)

Wall thermal modes (same geometry/mesh/flow, two BC modes; never both in one run):
  adiabatic   -> q''=0, gives adiabatic film effectiveness (BO objective)
  isothermal  -> fixed wall T, gives wall heat flux -> h / Stanton vs NASA
                 (CR-168015 no-film, CR-182133 film; Garg & Ameri 1997 method)
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

from bofm.cfd.mesh import DomainBounds, GEOMETRY_TO_SI, classify_split_case_boundaries

GAMMA = 1.4
R_AIR = 287.058  # J/(kg K)

# Kumar's C3X study uses the temperature-dependent air-property fits reported
# by Singh et al. over 100--2300 K. Fluent stores polynomial coefficients from
# the constant term upward: a0 + a1*T + ...
SINGH_AIR_POLYNOMIALS = {
    "specific_heat": (1.05e3, -3.21e-1, 8.07e-4, -4.81e-7, 9.08e-11),
    "thermal_conductivity": (2.88e-3, 8.30e-5, -2.40e-8, 7.99e-12),
    "viscosity": (1.06e-6, 6.85e-8, -4.04e-11, 1.70e-14),
}


def evaluate_polynomial(coefficients: tuple[float, ...], temperature_K: float) -> float:
    """Evaluate low-to-high-order Fluent polynomial coefficients."""
    value = 0.0
    for coefficient in reversed(coefficients):
        value = value * float(temperature_K) + coefficient
    return value


def singh_air_properties(temperature_K: float) -> dict[str, float]:
    """Return Kumar/Singh air Cp, conductivity, and viscosity at temperature."""
    temperature = float(temperature_K)
    if not 100.0 <= temperature <= 2300.0:
        raise ValueError("Singh air-property fits are valid only from 100 to 2300 K")
    return {
        name: evaluate_polynomial(coefficients, temperature)
        for name, coefficients in SINGH_AIR_POLYNOMIALS.items()
    }


def setup_temperature_dependent_air(solver, model: str | None) -> str:
    """Apply the selected air transport/thermal-property model in Fluent."""
    requested = str(model or "constant").lower()
    if requested in {"constant", "fluent_constant"}:
        return "fluent_constant"
    if requested != "singh_temperature_polynomials":
        raise ValueError(f"Unsupported air property model: {model!r}")

    air = solver.settings.setup.materials.fluid["air"]
    for property_name, coefficients in SINGH_AIR_POLYNOMIALS.items():
        getattr(air, property_name).set_state({
            "option": "polynomial",
            "polynomial": {
                "function_of": "temperature",
                "coefficients": list(coefficients),
            },
        })
    return requested


def load_baseline_config(path: str | Path | None = None) -> dict:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "configs" / "c3x_baseline.yaml"
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def isentropic_static_pressure(pt_pa: float, tt_k: float, mach: float) -> float:
    """Static pressure from total pressure and Mach (ideal gas, isentropic)."""
    factor = (1.0 + 0.5 * (GAMMA - 1.0) * mach * mach) ** (GAMMA / (GAMMA - 1.0))
    return pt_pa / factor


def isentropic_static_temperature(tt_k: float, mach: float) -> float:
    """Static temperature from total temperature and Mach (ideal gas)."""
    return tt_k / (1.0 + 0.5 * (GAMMA - 1.0) * mach * mach)


def exit_flow_angle_deg(config: dict) -> float:
    """Signed downstream flow angle [deg] in the cascade x-y coordinate system."""
    geom = config["geometry"]
    pd = geom.get("passage_domain", {})
    if "downstream_periodic_angle_deg" in pd:
        return float(pd["downstream_periodic_angle_deg"])
    return -abs(float(geom["air_exit_angle_deg"]))


def exit_velocity_components(config: dict) -> tuple[float, float, float]:
    """Return a reasonable exit-direction velocity vector for initialization."""
    cond = config["conditions"]
    mach = float(cond["exit_mach"])
    tt = float(cond["inlet_total_temperature_K"])
    ts = isentropic_static_temperature(tt, mach)
    vmag = mach * math.sqrt(GAMMA * R_AIR * ts)
    angle = math.radians(exit_flow_angle_deg(config))
    return vmag * math.cos(angle), vmag * math.sin(angle), 0.0


def scale_mesh_to_si(solver, factor: float = GEOMETRY_TO_SI) -> None:
    """Scale all mesh coordinates by `factor` (mm-magnitude -> metres)."""
    f = str(factor)
    # Fluent 2024 TUI: /mesh/scale x y z confirm
    solver.tui.mesh.scale(f, f, f, "yes")


def setup_physics(solver) -> None:
    """Compressible RANS, ideal gas, SST."""
    try:
        solver.tui.define.operating_conditions.operating_pressure("0")
    except Exception:
        pass
    solver.tui.define.models.energy("yes")
    solver.tui.define.models.viscous.kw_sst("yes")
    solver.tui.define.materials.change_create(
        "air", "air", "yes", "ideal-gas", "no", "no", "no", "no", "no", "no",
    )


def _rename_zone(solver, old: str, new: str) -> str:
    if old == new:
        return new
    solver.settings.setup.boundary_conditions.set_zone_name(
        zonename=old, newname=new,
    )
    return new


def split_merged_boundary(solver, wall_zone: str | None = None,
                          *, angle_deg: float = 1.0) -> None:
    """Split Fluent's merged external wall zone by feature angle."""
    if wall_zone is None:
        walls = list(solver.settings.setup.boundary_conditions.wall.keys())
        if not walls:
            raise RuntimeError("No wall zone found to split")
        wall_zone = walls[0]
    solver.tui.mesh.modify_zones.sep_face_zone_angle(
        wall_zone, str(angle_deg), "yes",
    )


def _create_translational_periodic(solver, low_name: str, high_name: str,
                                   translation: list[float], interface_name: str) -> None:
    """Create one non-conformal translational periodic interface (proven call)."""
    solver.settings.mesh.modify_zones.create_periodic_interface(
        periodic_method="non-conformal",
        interface_name=interface_name,
        zone_name=low_name,
        shadow_zone_name=high_name,
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
        create_matching=False,
        nonconformal_create_periodic=True,
    )


def prepare_boundary_zones(solver, split_case_path: str | Path,
                           bounds: DomainBounds, *, span_bc: str = "symmetry",
                           span_mm: float | None = None) -> dict:
    """Rename split zones, set inlet/outlet, span BC, and create periodic interfaces.

    `span_bc`:
      - 'symmetry' (default, no-film thin slice): span faces are symmetry planes.
      - 'periodic' (film): span faces become a translational periodic pair (z by
        span_mm). Film holes break spanwise symmetry, so the periodic slice needs
        spanwise periodicity, not symmetry. Requires span_mm.
    """
    groups = classify_split_case_boundaries(split_case_path, bounds)
    required = ("inlet", "outlet", "span_low", "span_high")
    missing = [name for name in required if len(groups[name]) != 1]
    if missing:
        raise RuntimeError(
            "Boundary classification failed: " +
            ", ".join(f"{name}={groups[name]}" for name in missing)
        )
    if len(groups["periodic_pairs"]) != 2:
        raise RuntimeError(f"Expected 2 periodic pairs, got {groups['periodic_pairs']}")

    bc = solver.settings.setup.boundary_conditions
    stable = {
        "inlet": _rename_zone(solver, groups["inlet"][0], "inlet"),
        "outlet": _rename_zone(solver, groups["outlet"][0], "outlet"),
        "span_low": _rename_zone(solver, groups["span_low"][0], "span_low"),
        "span_high": _rename_zone(solver, groups["span_high"][0], "span_high"),
    }
    solver.tui.define.boundary_conditions.zone_type("inlet", "pressure-inlet")
    solver.tui.define.boundary_conditions.zone_type("outlet", "pressure-outlet")

    if span_bc == "symmetry":
        solver.tui.define.boundary_conditions.zone_type("span_low", "symmetry")
        solver.tui.define.boundary_conditions.zone_type("span_high", "symmetry")
    elif span_bc == "periodic":
        if span_mm is None:
            raise ValueError("span_bc='periodic' needs span_mm (z-translation length)")
        span_m = float(span_mm) * GEOMETRY_TO_SI
        _create_translational_periodic(
            solver, stable["span_low"], stable["span_high"],
            [0.0, 0.0, span_m], "span_periodic_interface",
        )
    else:
        raise ValueError(f"unknown span_bc {span_bc!r} (use 'symmetry' or 'periodic')")

    pitch_m = bounds.pitch_mm * GEOMETRY_TO_SI
    periodic_pairs = []
    for i, (low, high) in enumerate(groups["periodic_pairs"]):
        low_name = _rename_zone(solver, low, f"periodic_low_{i}")
        high_name = _rename_zone(solver, high, f"periodic_high_{i}")
        _create_translational_periodic(
            solver, low_name, high_name, [0.0, pitch_m, 0.0],
            f"periodic_interface_{i}",
        )
        periodic_pairs.append((low_name, high_name))

    stable["periodic_pairs"] = periodic_pairs
    stable["span_bc"] = span_bc
    stable["vane_wall_zones"] = list(bc.wall.keys())
    return {"classified": groups, "stable": stable}


def wall_thermal_state(config: dict, wall_thermal: str | None = None,
                       wall_temperature_K: float | None = None) -> dict:
    """Build the Fluent wall 'thermal' state dict for the chosen mode.

    Mode and temperature resolve from the explicit args first, else from
    `config['validation']`. Default is adiabatic so the BO loop is unchanged.

    - 'adiabatic'  : zero heat flux. Adiabatic film effectiveness is the BO
                     objective; the correlation prior predicts that eta.
    - 'isothermal' : fixed wall temperature. The resulting wall heat flux gives
                     h / Stanton for validation against NASA CR-168015 /
                     CR-182133 (Garg & Ameri 1997 method).
    """
    val = config.get("validation", {}) or {}
    mode = (wall_thermal or val.get("wall_thermal") or "adiabatic").lower()
    if mode == "adiabatic":
        return {"thermal_condition": "Heat Flux",
                "heat_flux": {"option": "value", "value": 0}}
    if mode == "isothermal":
        twall = wall_temperature_K
        if twall is None:
            twall = val.get("wall_temperature_K")
        if twall is None:
            raise ValueError(
                "isothermal wall needs a temperature: pass wall_temperature_K or "
                "set validation.wall_temperature_K in c3x_baseline.yaml "
                "(measured C3X wall temperature for the validated run)."
            )
        # Same settings schema as the heat-flux branch; pyfluent wall thermal
        # uses 'Temperature' + a 'temperature' value. Confirm on first run.
        return {"thermal_condition": "Temperature",
                "temperature": {"option": "value", "value": float(twall)}}
    raise ValueError(
        f"unknown wall_thermal mode {mode!r} (use 'adiabatic' or 'isothermal')"
    )


def setup_bcs(solver, config: dict, *, wall_thermal: str | None = None,
              wall_temperature_K: float | None = None) -> None:
    """Assign inlet/outlet values from c3x_baseline.yaml after zones are prepared.

    `wall_thermal` ('adiabatic'|'isothermal') and `wall_temperature_K` override
    the `validation` block in the config; default keeps walls adiabatic.
    """
    cond = config["conditions"]
    pt = float(cond["inlet_total_pressure_kPa"]) * 1000.0
    tt = float(cond["inlet_total_temperature_K"])
    ma_in = float(cond["inlet_mach"])
    ma_out = float(cond["exit_mach"])
    tu_pct = float(cond["inlet_turbulence_intensity_pct"])

    p_out = isentropic_static_pressure(pt, tt, ma_out)

    bc = solver.settings.setup.boundary_conditions
    bc.pressure_inlet["inlet"].set_state({
        "momentum": {
            "gauge_total_pressure": {"option": "value", "value": pt},
            "supersonic_or_initial_gauge_pressure": {"option": "value", "value": pt},
            "direction_specification_method": "Normal to Boundary",
        },
        "thermal": {
            "total_temperature": {"option": "value", "value": tt},
        },
        "turbulence": {
            "turbulence_specification": "Intensity and Viscosity Ratio",
            "turbulent_intensity": tu_pct / 100.0,
            "turbulent_viscosity_ratio": 10,
        },
    })

    bc.pressure_outlet["outlet"].set_state({
        "momentum": {
            "gauge_pressure": {"option": "value", "value": p_out},
            "backflow_dir_spec_method": "Normal to Boundary",
        },
        "thermal": {
            "backflow_total_temperature": {"option": "value", "value": tt},
        },
        "turbulence": {
            "turbulence_specification": "Intensity and Viscosity Ratio",
            "backflow_turbulent_intensity": tu_pct / 100.0,
            "backflow_turbulent_viscosity_ratio": 10,
        },
    })
    thermal = wall_thermal_state(config, wall_thermal, wall_temperature_K)
    for wall_name in list(bc.wall.keys()):
        bc.wall[wall_name].set_state({
            "momentum": {
                "wall_motion": "Stationary Wall",
                "shear_condition": "No Slip",
            },
            "thermal": thermal,
            "turbulence": {
                "roughness_model": "Standard",
                "roughness_height": {"option": "value", "value": 0},
                "roughness_const": {"option": "value", "value": 0.5},
            },
        })


def _fluid_cell_zones(solver) -> list[str]:
    try:
        return sorted(str(name) for name in solver.settings.setup.cell_zone_conditions.fluid.keys())
    except Exception:
        return []


def patch_exit_velocity_initial_guess(solver, config: dict) -> tuple[float, float, float] | None:
    """Patch the fluid zone with an exit-directed velocity after hybrid init."""
    cell_zones = _fluid_cell_zones(solver)
    if not cell_zones:
        return None
    ux, uy, uz = exit_velocity_components(config)
    patch = solver.settings.solution.initialization.patch.calculate_patch
    for variable, value in (
        ("x-velocity", ux),
        ("y-velocity", uy),
        ("z-velocity", uz),
    ):
        patch(
            domain="mixture",
            cell_zones=cell_zones,
            registers=[],
            variable=variable,
            reference_frame="Absolute",
            use_custom_field_function=False,
            custom_field_function_name="",
            value=float(value),
        )
    return ux, uy, uz


def initialize_and_iterate(solver, n_iter: int = 200, config: dict | None = None) -> None:
    solver.tui.solve.initialize.hyb_initialization()
    if config is not None:
        patch_exit_velocity_initial_guess(solver, config)
    solver.tui.solve.iterate(str(n_iter))


def report_zones(solver) -> list[str]:
    """Return face zone names present in the loaded mesh."""
    try:
        zones = list(solver.settings.setup.boundary_conditions.keys())
        return sorted(str(z) for z in zones)
    except Exception:
        return []


def setup_nofilm_case(solver, msh_path: str | Path, passage_json: str | Path,
                      config: dict | None = None, *, span_mm: float = 3.96,
                      n_iter: int = 0, split_case_path: str | Path | None = None,
                      wall_thermal: str | None = None,
                      wall_temperature_K: float | None = None) -> DomainBounds:
    """Read mesh in meshing mode, switch to solver, set physics/BCs.

    Prefer reading a .cas.h5 written after meshing (see scripts/test_volume_mesh.py).
    Fluent auto-scales mm-magnitude coordinates to metres on switch — do not scale again.
    """
    config = config or load_baseline_config()
    bounds = DomainBounds.from_passage_json(passage_json, span_mm=span_mm)

    # read_mesh only exists in meshing mode (PyFluent 0.20)
    if hasattr(solver.tui.file, "read_mesh"):
        solver.tui.file.read_mesh(str(Path(msh_path).resolve()))
        solver.tui.switch_to_solution_mode("yes")
    else:
        solver.tui.file.read_case(str(Path(msh_path).resolve()))

    setup_physics(solver)
    if split_case_path:
        split_merged_boundary(solver)
        solver.tui.file.write_case(str(Path(split_case_path).resolve()))
        prepare_boundary_zones(solver, split_case_path, bounds)
    setup_bcs(solver, config, wall_thermal=wall_thermal,
              wall_temperature_K=wall_temperature_K)

    if n_iter > 0:
        initialize_and_iterate(solver, n_iter, config=config)
    return bounds
