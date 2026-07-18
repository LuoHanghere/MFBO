"""NASA 44344 boundary-condition reference values for Workbench / Fluent GUI."""
from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def load_workbench_config(path: Path | None = None) -> dict:
    p = path or (ROOT / "configs" / "c3x_workbench.yaml")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def load_simulation_case(case_id: str | None = None) -> dict:
    cfg = yaml.safe_load((ROOT / "configs" / "c3x_simulation_cases.yaml").read_text(encoding="utf-8"))
    key = case_id or cfg["default_case"]
    return {"id": key, **cfg["cases"][key]}


def workbench_inlet_bc(case: dict, wb: dict | None = None) -> dict:
    """Return Workbench boundary states for the selected simulation case."""
    wb = wb or load_workbench_config()
    ms = case["mainstream"]
    pt = float(ms["inlet_total_pressure_Pa"])
    tt = float(ms["inlet_total_temperature_K"])
    p_out = float(ms["outlet_static_pressure_Pa"])
    tu_pct = float(ms.get("inlet_turbulence_intensity_pct", 6.5))
    coolant_boundary = case.get("coolant_boundary", {})
    coolant_mode = str(coolant_boundary.get("mode", "pressure_ratio"))
    mass_flow_key = str(
        coolant_boundary.get("mass_flow_key", "periodic_14p85mm_mass_flow_kg_s")
    )
    if coolant_mode not in {"pressure_ratio", "measured_mass_flow", "zero_mass_flow"}:
        raise ValueError(f"Unsupported coolant boundary mode: {coolant_mode}")

    zones = {}
    zones["inlet"] = {
        "type": "pressure-inlet",
        "gauge_total_pressure_Pa": pt,
        "total_temperature_K": tt,
        "turbulence_intensity": tu_pct / 100.0,
    }
    for zname, spec in wb["face_zones"]["coolant"].items():
        region = spec["region"]
        cool = case["coolant"][region]
        use_mass_flow = coolant_mode in {"measured_mass_flow", "zero_mass_flow"}
        zone = {
            "type": "mass-flow-inlet" if use_mass_flow else "pressure-inlet",
            "gauge_total_pressure_Pa": float(cool["pc_over_pt"]) * pt,
            "total_temperature_K": float(cool["total_temperature_K"]),
            "turbulence_intensity": tu_pct / 100.0,
            "region": region,
        }
        if coolant_mode == "zero_mass_flow":
            zone["mass_flow_rate_kg_s"] = 0.0
            zone["mass_flow_source_key"] = "zero_mass_flow"
        elif coolant_mode == "measured_mass_flow":
            if mass_flow_key not in cool:
                raise KeyError(
                    f"Coolant region {region!r} has no measured mass-flow key {mass_flow_key!r}"
                )
            zone["mass_flow_rate_kg_s"] = float(cool[mass_flow_key])
            zone["mass_flow_source_key"] = mass_flow_key
        zones[zname] = zone
    zones["outlet"] = {
        "type": "pressure-outlet",
        "gauge_pressure_Pa": p_out,
    }
    return zones


def format_bc_table(case_id: str | None = None) -> str:
    case = load_simulation_case(case_id)
    wb = load_workbench_config()
    bcs = workbench_inlet_bc(case, wb)
    lines = [
        f"Workbench Route B — Fluent BC reference ({case['id']}, run {case.get('run_code', '?')})",
        f"Purpose: {case.get('purpose', '')}",
        "",
        "Zone            Type              Value",
        "-" * 72,
    ]
    for zname in ("inlet", "qian", "ss", "ps", "outlet"):
        bc = bcs[zname]
        if bc["type"] == "pressure-outlet":
            lines.append(f"{zname:16}  pressure-outlet   P_gauge = {bc['gauge_pressure_Pa']:.3f} Pa")
        elif bc["type"] == "mass-flow-inlet":
            lines.append(
                f"{zname:16}  mass-flow-inlet  mdot = {bc['mass_flow_rate_kg_s']:.10f} kg/s, "
                f"Tt = {bc['total_temperature_K']:.2f} K  "
                f"(Pc target = {bc['gauge_total_pressure_Pa']:.3f} Pa, {bc['region']})"
            )
        else:
            extra = f"  ({bc['region']})" if bc.get("region") else ""
            lines.append(
                f"{zname:16}  pressure-inlet    Pt_gauge = {bc['gauge_total_pressure_Pa']:.3f} Pa, "
                f"Tt = {bc['total_temperature_K']:.2f} K{extra}"
            )
    wall_doc = case.get("walls", {})
    wall_mode = wall_doc.get(
        "thermal_mode", wall_doc.get("optimization_mode", "adiabatic")
    )
    wall_temperature = wall_doc.get("temperature_K")
    wall_text = f"Walls: {wall_mode} no-slip"
    if wall_temperature is not None:
        wall_text += f", T_wall = {float(wall_temperature):.2f} K"
    lines.extend([
        "",
        wall_text + ".",
        "Periodic: create translational pair periodic_low <-> periodic_high.",
        f"Tu = {case['mainstream'].get('inlet_turbulence_intensity_pct', 6.5)}% on all inlets.",
    ])
    return "\n".join(lines)
