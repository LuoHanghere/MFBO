"""No-film C3X cascade RANS setup for CR-168015 validation.

Mesh note: the watertight .sat import stores mm-magnitude coordinates but Fluent
reads ACIS numbers as metres. Scale the grid by mesh.GEOMETRY_TO_SI (0.001)
before setting BCs so pitch/span/chord are physically correct.

BC layout (from build_fluid_domain + mesh.tag_zones):
  inlet / outlet          : cascade in/out planes
  periodic_low / high     : translational pitchwise periodicity (+pitch in y)
  span_low / span_high    : symmetry (thin midspan slice, no-film 2D-like case)
  vane_wall               : adiabatic no-slip wall
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

from bofm.cfd.mesh import DomainBounds, GEOMETRY_TO_SI, classify_split_case_boundaries

GAMMA = 1.4
R_AIR = 287.058  # J/(kg K)


def load_baseline_config(path: str | Path | None = None) -> dict:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "configs" / "c3x_baseline.yaml"
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def isentropic_static_pressure(pt_pa: float, tt_k: float, mach: float) -> float:
    """Static pressure from total pressure and Mach (ideal gas, isentropic)."""
    factor = (1.0 + 0.5 * (GAMMA - 1.0) * mach * mach) ** (GAMMA / (GAMMA - 1.0))
    return pt_pa / factor


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


def prepare_boundary_zones(solver, split_case_path: str | Path,
                           bounds: DomainBounds) -> dict:
    """Rename split zones, set inlet/outlet/symmetry, and create periodic interfaces."""
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
    solver.tui.define.boundary_conditions.zone_type("span_low", "symmetry")
    solver.tui.define.boundary_conditions.zone_type("span_high", "symmetry")

    pitch_m = bounds.pitch_mm * GEOMETRY_TO_SI
    periodic_pairs = []
    for i, (low, high) in enumerate(groups["periodic_pairs"]):
        low_name = _rename_zone(solver, low, f"periodic_low_{i}")
        high_name = _rename_zone(solver, high, f"periodic_high_{i}")
        solver.settings.mesh.modify_zones.create_periodic_interface(
            periodic_method="non-conformal",
            interface_name=f"periodic_interface_{i}",
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
            translation=[0.0, pitch_m, 0.0],
            create_periodic=True,
            auto_offset=False,
            nonconformal_angle=0.0,
            nonconformal_translation=[0.0, pitch_m, 0.0],
            create_matching=False,
            nonconformal_create_periodic=True,
        )
        periodic_pairs.append((low_name, high_name))

    stable["periodic_pairs"] = periodic_pairs
    stable["vane_wall_zones"] = list(bc.wall.keys())
    return {"classified": groups, "stable": stable}


def setup_bcs(solver, config: dict) -> None:
    """Assign inlet/outlet values from c3x_baseline.yaml after zones are prepared."""
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
    for wall_name in list(bc.wall.keys()):
        bc.wall[wall_name].set_state({
            "momentum": {
                "wall_motion": "Stationary Wall",
                "shear_condition": "No Slip",
            },
            "thermal": {
                "thermal_condition": "Heat Flux",
                "heat_flux": {"option": "value", "value": 0},
            },
            "turbulence": {
                "roughness_model": "Standard",
                "roughness_height": {"option": "value", "value": 0},
                "roughness_const": {"option": "value", "value": 0.5},
            },
        })


def initialize_and_iterate(solver, n_iter: int = 200) -> None:
    solver.tui.solve.initialize.hyb_initialization()
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
                      n_iter: int = 0, split_case_path: str | Path | None = None) -> DomainBounds:
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
    setup_bcs(solver, config)

    if n_iter > 0:
        initialize_and_iterate(solver, n_iter)
    return bounds
