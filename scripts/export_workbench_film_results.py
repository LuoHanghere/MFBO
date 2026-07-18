"""Export Workbench film-cooling result summaries for validation and BO.

This script reads a prepared Fluent case/data pair and writes compact JSON/CSV
summaries under a post-processing directory.  It is intentionally conservative:
fields or report quantities that Fluent does not expose are recorded as missing
rather than causing the whole export to fail.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
import numpy as np
from scipy.spatial import cKDTree
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

import bofm.cfd.fluent as F
from bofm.geometry.film_holes import NASA_FILM_HOLES_UV_CM
from bofm.geometry.profile import densify_profile
from bofm.geometry import parametrization as P


DEFAULT_WALL_PATTERNS = ["*vane_wall*", "vane_wall"]
WALL_FIELDS = ["wall-temperature", "temperature", "y-plus"]
HEAT_TRANSFER_FIELDS = [
    "heat-flux",
    "stanton-number",
    "heat-transfer-coef",
    "heat-transfer-coef-wall-adj",
    "wall-adjacent-temperature",
]
PRESSURE_FIELDS = ["pressure", "absolute-pressure", "total-pressure"]
ZONE_MAP = {
    "qian": "showerhead",
    "ss": "suction",
    "ps": "pressure",
}
DEFAULT_PROTECTED_XMIN = {
    "pressure": 0.26530,
    "suction": 0.37638,
}


def _surface_ids(meta: dict) -> list[int]:
    return [int(i) for i in meta.get("surface_id", [])]


def scalar_values(field_data) -> list[float]:
    return [float(item.scalar_data) for item in field_data.data]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    xs = sorted(values)
    return xs[min(len(xs) - 1, max(0, int(q * (len(xs) - 1))))]


def summarize_values(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "min": math.nan, "mean": math.nan, "p95": math.nan, "max": math.nan}
    return {
        "count": len(values),
        "min": min(values),
        "mean": statistics.fmean(values),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }


def load_case_config(path: Path, case_name: str) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc["cases"][case_name]


def coolant_reference_temperature(sim_case: dict[str, Any]) -> dict[str, Any]:
    rows = []
    num = 0.0
    den = 0.0
    for region, data in sim_case.get("coolant", {}).items():
        temp = float(data["total_temperature_K"])
        mdot = float(data.get("periodic_14p85mm_mass_flow_kg_s")
                     or data.get("full_vane_mass_flow_kg_s")
                     or 0.0)
        rows.append({"region": region, "total_temperature_K": temp, "weight_kg_s": mdot})
        num += temp * mdot
        den += mdot
    if den > 0.0:
        return {"method": "coolant target mass-flow weighted", "value_K": num / den, "components": rows}
    vals = [r["total_temperature_K"] for r in rows]
    return {"method": "simple mean coolant temperature", "value_K": statistics.fmean(vals), "components": rows}


def wall_surfaces(solver) -> dict[str, dict]:
    surfaces = solver.fields.field_info.get_surfaces_info()
    return {name: meta for name, meta in surfaces.items() if meta.get("zone_type") == "wall"}


def select_walls(walls: dict[str, dict], patterns: list[str]) -> dict[str, dict]:
    selected = {
        name: meta
        for name, meta in walls.items()
        if any(fnmatch(name, pat) for pat in patterns)
    }
    return selected or walls


def select_named_surfaces(solver, names: list[str]) -> dict[str, dict]:
    surfaces = solver.fields.field_info.get_surfaces_info()
    return {name: meta for name, meta in surfaces.items() if name in names}


def available_fields(solver, requested: list[str]) -> list[str]:
    scalars = solver.fields.field_info.get_scalar_fields_info()
    return [name for name in requested if name in scalars]


def scalar_summary_on_surfaces(solver, surfaces: dict[str, dict], field_name: str) -> dict[str, Any] | None:
    field_data = solver.fields.field_data
    rows = []
    all_values: list[float] = []
    for name, meta in sorted(surfaces.items()):
        ids = _surface_ids(meta)
        if not ids:
            continue
        try:
            data_by_id = field_data.get_scalar_field_data(
                field_name=field_name,
                surface_ids=ids,
                node_value=True,
            )
        except Exception:
            return None
        values: list[float] = []
        for values_for_id in data_by_id.values():
            vals = scalar_values(values_for_id)
            values.extend(vals)
            all_values.extend(vals)
        if values:
            row = {"surface": name}
            row.update(summarize_values(values))
            rows.append(row)
    if not all_values:
        return None
    out = {
        "field": field_name,
        "surfaces": rows,
    }
    out.update(summarize_values(all_values))
    return out


def _single_surface_data(data_by_id: dict, surface_id: int):
    if surface_id in data_by_id:
        return data_by_id[surface_id]
    if str(surface_id) in data_by_id:
        return data_by_id[str(surface_id)]
    raise KeyError(f"Surface id {surface_id} missing from Fluent field response")


def wall_face_rows(
    solver,
    surfaces: dict[str, dict],
    field_name: str,
    tg_ref: float,
    tc_ref: float,
) -> list[dict[str, Any]]:
    """Return one row per wall face with area, centroid, temperature, and eta."""
    from ansys.fluent.core.services.field_data import SurfaceDataType

    denom = tg_ref - tc_ref
    if abs(denom) < 1e-12:
        raise ValueError("Tg_ref and Tc_ref are equal; eta is undefined")

    field_data = solver.fields.field_data
    rows: list[dict[str, Any]] = []
    for surface_name, meta in sorted(surfaces.items()):
        for surface_id in _surface_ids(meta):
            temp_map = field_data.get_scalar_field_data(
                field_name=field_name,
                surface_ids=[surface_id],
                node_value=False,
                boundary_value=True,
            )
            centroid_map = field_data.get_surface_data(
                data_type=SurfaceDataType.FacesCentroid,
                surface_ids=[surface_id],
            )
            normal_map = field_data.get_surface_data(
                data_type=SurfaceDataType.FacesNormal,
                surface_ids=[surface_id],
            )
            temperatures = scalar_values(_single_surface_data(temp_map, surface_id))
            centroids = _single_surface_data(centroid_map, surface_id).data
            normals = _single_surface_data(normal_map, surface_id).data
            if not (len(temperatures) == len(centroids) == len(normals)):
                raise ValueError(
                    f"Face-data length mismatch for {surface_name}/{surface_id}: "
                    f"temperature={len(temperatures)}, centroid={len(centroids)}, "
                    f"normal={len(normals)}"
                )
            for face_index, (temp, center, normal) in enumerate(
                zip(temperatures, centroids, normals)
            ):
                area = math.sqrt(normal.x ** 2 + normal.y ** 2 + normal.z ** 2)
                if not math.isfinite(area) or area <= 0.0:
                    continue
                rows.append({
                    "surface": surface_name,
                    "surface_id": surface_id,
                    "face_index": face_index,
                    "x_m": float(center.x),
                    "y_m": float(center.y),
                    "z_m": float(center.z),
                    "face_area_m2": float(area),
                    "Taw_K": float(temp),
                    "eta": float((tg_ref - temp) / denom),
                })
    return rows


def surface_scalar_face_rows(
    solver,
    surfaces: dict[str, dict],
    field_name: str,
    value_key: str,
) -> list[dict[str, Any]]:
    """Return one row per boundary face for a scalar and its geometry."""
    from ansys.fluent.core.services.field_data import SurfaceDataType

    field_data = solver.fields.field_data
    rows: list[dict[str, Any]] = []
    for surface_name, meta in sorted(surfaces.items()):
        for surface_id in _surface_ids(meta):
            scalar_map = field_data.get_scalar_field_data(
                field_name=field_name,
                surface_ids=[surface_id],
                node_value=False,
                boundary_value=True,
            )
            centroid_map = field_data.get_surface_data(
                data_type=SurfaceDataType.FacesCentroid,
                surface_ids=[surface_id],
            )
            normal_map = field_data.get_surface_data(
                data_type=SurfaceDataType.FacesNormal,
                surface_ids=[surface_id],
            )
            values = scalar_values(_single_surface_data(scalar_map, surface_id))
            centroids = _single_surface_data(centroid_map, surface_id).data
            normals = _single_surface_data(normal_map, surface_id).data
            if not (len(values) == len(centroids) == len(normals)):
                raise ValueError(
                    f"Face-data length mismatch for {surface_name}/{surface_id}: "
                    f"scalar={len(values)}, centroid={len(centroids)}, normal={len(normals)}"
                )
            for face_index, (value, center, normal) in enumerate(
                zip(values, centroids, normals)
            ):
                area = math.sqrt(normal.x ** 2 + normal.y ** 2 + normal.z ** 2)
                if not math.isfinite(area) or area <= 0.0:
                    continue
                rows.append({
                    "surface": surface_name,
                    "surface_id": surface_id,
                    "face_index": face_index,
                    "x_m": float(center.x),
                    "y_m": float(center.y),
                    "z_m": float(center.z),
                    "face_area_m2": float(area),
                    value_key: float(value),
                })
    return rows


def _load_xy_csv(path: Path) -> np.ndarray:
    with path.open("r", encoding="utf-8") as stream:
        reader = csv.DictReader(line for line in stream if not line.lstrip().startswith("#"))
        rows = [[float(row["x_mm"]), float(row["y_mm"])] for row in reader]
    return np.asarray(rows, dtype=float)


def annotate_kumar_coordinates(
    rows: list[dict[str, Any]],
    profile_csv: Path,
    uv_transform_json: Path,
    axial_chord_mm: float,
    hole_diameter_mm: float,
    span_mid_mm: float,
) -> None:
    """Add cascade X/Cax, surface side, and full-period Z/D to face rows."""
    if not rows:
        return
    raw_profile = P.clean_profile(P.load_profile(profile_csv))
    cascade_profile = densify_profile(raw_profile, n_per_surface=220, cluster=0.5)
    surfaces = P.build_surfaces(cascade_profile)
    suction_xy = np.asarray(surfaces["suction"].xy, dtype=float)
    pressure_xy = np.asarray(surfaces["pressure"].xy, dtype=float)
    le_xy = suction_xy[0]

    meta = json.loads(uv_transform_json.read_text(encoding="utf-8"))
    origin = meta["model_origin"]
    fit = meta["fit_used_only_to_transform_existing_blade"]
    theta = math.radians(float(fit["angle_deg"]))
    reflection = float(fit["reflection"])
    scale = float(fit["scale"])
    c, s = math.cos(theta), math.sin(theta)
    matrix = scale * np.array([[c, -s], [s, c]]) @ np.array(
        [[1.0, 0.0], [0.0, reflection]], dtype=float
    )
    h16_uv_cm = np.asarray(NASA_FILM_HOLES_UV_CM[16], dtype=float)

    model_xy_mm = np.array(
        [[1000.0 * float(row["x_m"]), 1000.0 * float(row["y_m"])] for row in rows]
    )
    report_v_mm = model_xy_mm[:, 0] + float(origin["v_report_origin_mm"])
    report_u_mm = model_xy_mm[:, 1] + float(origin["u_report_origin_mm"])
    uv_cm = np.column_stack([report_u_mm / 10.0, report_v_mm / 10.0])
    cascade_from_uv = (matrix @ (uv_cm - h16_uv_cm).T).T + le_xy

    # Route-A production geometry is currently written in the original cascade
    # x/y frame, while older UV-frame assets use x=V and y=U.  Select the frame
    # by the median distance of wall faces to the known C3X contour.
    profile_tree = cKDTree(np.vstack([suction_xy, pressure_xy]))
    direct_score = float(np.median(profile_tree.query(model_xy_mm)[0]))
    uv_score = float(np.median(profile_tree.query(cascade_from_uv)[0]))
    if direct_score <= uv_score:
        cascade_xy = model_xy_mm
        coordinate_frame = "cascade_xy_direct"
        mapping_score_mm = direct_score
    else:
        cascade_xy = cascade_from_uv
        coordinate_frame = "uv_model_to_cascade"
        mapping_score_mm = uv_score

    suction_dist, suction_index = cKDTree(suction_xy).query(cascade_xy)
    pressure_dist, pressure_index = cKDTree(pressure_xy).query(cascade_xy)
    is_suction = suction_dist <= pressure_dist
    x_over_cax = (cascade_xy[:, 0] - float(le_xy[0])) / float(axial_chord_mm)
    suction_arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(suction_xy, axis=0), axis=1))])
    pressure_arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pressure_xy, axis=0), axis=1))])

    for i, row in enumerate(rows):
        side = "suction" if bool(is_suction[i]) else "pressure"
        row["side"] = side
        row["coordinate_frame"] = coordinate_frame
        row["profile_mapping_distance_median_mm"] = mapping_score_mm
        row["cascade_x_mm"] = float(cascade_xy[i, 0])
        row["cascade_y_mm"] = float(cascade_xy[i, 1])
        row["X_over_Cax"] = float(x_over_cax[i])
        row["signed_X_over_Cax"] = float(x_over_cax[i] if side == "suction" else -x_over_cax[i])
        if side == "suction":
            row["surface_distance_pct"] = float(100.0 * suction_arc[suction_index[i]] / suction_arc[-1])
        else:
            row["surface_distance_pct"] = float(100.0 * pressure_arc[pressure_index[i]] / pressure_arc[-1])
        row["Z_over_D"] = float((1000.0 * float(row["z_m"]) - span_mid_mm) / hole_diameter_mm)


def compare_nasa_surface_pressure(
    face_rows: list[dict[str, Any]], reference_csv: Path, inlet_total_pressure_pa: float,
    window_pct: float = 0.5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compare span-averaged wall pressure with NASA CR-182133 Table VII."""
    with reference_csv.open("r", encoding="utf-8") as stream:
        reference = list(csv.DictReader(stream))
    comparison: list[dict[str, Any]] = []
    for ref in reference:
        side = str(ref["side"])
        target = float(ref["surface_distance_pct"])
        candidates = [
            row for row in face_rows
            if row.get("side") == side
            and abs(float(row["surface_distance_pct"]) - target) <= window_pct
        ]
        if not candidates:
            same_side = [row for row in face_rows if row.get("side") == side]
            nearest_delta = min(
                abs(float(row["surface_distance_pct"]) - target) for row in same_side
            )
            candidates = [
                row for row in same_side
                if abs(float(row["surface_distance_pct"]) - target) <= nearest_delta + 1e-12
            ]
        pressure_pa = _weighted_mean(candidates, "static_pressure_Pa")
        predicted = pressure_pa / inlet_total_pressure_pa
        measured = float(ref["ps_over_pt_ma090"])
        comparison.append({
            "side": side,
            "surface_distance_pct": target,
            "axial_chord_pct": float(ref["axial_chord_pct"]),
            "nasa_ps_over_pt_ma090": measured,
            "cfd_ps_over_pt": predicted,
            "error": predicted - measured,
            "abs_error": abs(predicted - measured),
            "sample_window_pct": window_pct,
            "face_count": len(candidates),
        })
    errors = np.asarray([float(row["error"]) for row in comparison], dtype=float)
    summary: dict[str, Any] = {
        "reference": "NASA CR-182133 Table VII, Ma2=0.90 column",
        "normalization": f"CFD static pressure / inlet total pressure ({inlet_total_pressure_pa:.6g} Pa)",
        "span_averaging": f"face-area weighted within +/-{window_pct:g}% surface distance",
        "point_count": len(comparison),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "max_abs_error": float(np.max(np.abs(errors))),
        "sides": {},
    }
    for side in ("pressure", "suction"):
        side_errors = np.asarray(
            [float(row["error"]) for row in comparison if row["side"] == side], dtype=float
        )
        summary["sides"][side] = {
            "point_count": int(side_errors.size),
            "mae": float(np.mean(np.abs(side_errors))),
            "rmse": float(np.sqrt(np.mean(side_errors ** 2))),
            "max_abs_error": float(np.max(np.abs(side_errors))),
        }
    return comparison, summary


def _weighted_mean(rows: list[dict[str, Any]], value_key: str) -> float:
    area = sum(float(row["face_area_m2"]) for row in rows)
    if area <= 0.0:
        return math.nan
    return sum(
        float(row["face_area_m2"]) * float(row[value_key]) for row in rows
    ) / area


def eta_summary(face_rows: list[dict[str, Any]], tg_ref: float, tc_ref: float) -> dict[str, Any]:
    denom = tg_ref - tc_ref
    if abs(denom) < 1e-12:
        raise ValueError("Tg_ref and Tc_ref are equal; eta is undefined")
    surface_rows = []
    names = sorted({str(row["surface"]) for row in face_rows})
    for name in names:
        subset = [row for row in face_rows if row["surface"] == name]
        surface_rows.append({
            "surface": name,
            "face_count": len(subset),
            "area_m2": sum(float(row["face_area_m2"]) for row in subset),
            "Taw_area_weighted_K": _weighted_mean(subset, "Taw_K"),
            "eta_area_weighted": _weighted_mean(subset, "eta"),
        })
    side_rows = []
    for side in ("pressure", "suction"):
        subset = [row for row in face_rows if row.get("side") == side]
        if subset:
            side_rows.append({
                "side": side,
                "face_count": len(subset),
                "area_m2": sum(float(row["face_area_m2"]) for row in subset),
                "Taw_area_weighted_K": _weighted_mean(subset, "Taw_K"),
                "eta_area_weighted": _weighted_mean(subset, "eta"),
            })
    return {
        "definition": "eta = (Tg_ref - Taw) / (Tg_ref - Tc_ref)",
        "averaging": "face-area weighted using the magnitude of Fluent face-area vectors",
        "Tg_ref_K": tg_ref,
        "Tc_ref_K": tc_ref,
        "face_count": len(face_rows),
        "area_m2": sum(float(row["face_area_m2"]) for row in face_rows),
        "Taw_area_weighted_K": _weighted_mean(face_rows, "Taw_K"),
        "eta_bar": _weighted_mean(face_rows, "eta"),
        "surfaces": surface_rows,
        "sides": side_rows,
    }


def protected_eta_summary(
    face_rows: list[dict[str, Any]],
    tg_ref: float,
    tc_ref: float,
    pressure_xmin: float = DEFAULT_PROTECTED_XMIN["pressure"],
    suction_xmin: float = DEFAULT_PROTECTED_XMIN["suction"],
) -> dict[str, Any]:
    """Return eta on one frozen downstream region shared by every BO design."""
    thresholds = {"pressure": float(pressure_xmin), "suction": float(suction_xmin)}
    selected = [
        row for row in face_rows
        if row.get("side") in thresholds
        and float(row.get("X_over_Cax", -math.inf)) >= thresholds[str(row["side"])]
    ]
    if not selected:
        raise ValueError("protected-area mask selected no wall faces")
    summary = eta_summary(selected, tg_ref, tc_ref)
    summary.update({
        "region": "fixed downstream controllable area",
        "mask": {
            "pressure": f"X/Cax >= {thresholds['pressure']:.5f}",
            "suction": f"X/Cax >= {thresholds['suction']:.5f}",
        },
        "fixed_across_designs": True,
        "note": "Thresholds are frozen at baseline first-variable-row axial stations.",
    })
    return summary


def lateral_eta_profile(
    face_rows: list[dict[str, Any]],
    side: str,
    station: float,
    tolerance: float,
    bins: int,
) -> list[dict[str, Any]]:
    selected = [row for row in face_rows if row.get("side") == side]
    if len(selected) < 10:
        return []
    points = np.array([
        [float(row["X_over_Cax"]), float(row["Z_over_D"])] for row in selected
    ])
    eta_values = np.array([float(row["eta"]) for row in selected])
    temp_values = np.array([float(row["Taw_K"]) for row in selected])
    z_min = float(np.min(points[:, 1]))
    z_max = float(np.max(points[:, 1]))
    # Query just inside the face-centroid envelope. This avoids extrapolating
    # across periodic edges while retaining the full -7.5D..7.5D span.
    pad = max((z_max - z_min) * 1e-6, 1e-8)
    z_query = np.linspace(z_min + pad, z_max - pad, int(bins))
    query = np.column_stack([np.full_like(z_query, station), z_query])
    eta_linear = np.asarray(LinearNDInterpolator(points, eta_values)(query), dtype=float)
    temp_linear = np.asarray(LinearNDInterpolator(points, temp_values)(query), dtype=float)
    eta_nearest = np.asarray(NearestNDInterpolator(points, eta_values)(query), dtype=float)
    temp_nearest = np.asarray(NearestNDInterpolator(points, temp_values)(query), dtype=float)
    eta_query = np.where(np.isfinite(eta_linear), eta_linear, eta_nearest)
    temp_query = np.where(np.isfinite(temp_linear), temp_linear, temp_nearest)
    output = []
    for z_value, temp_value, eta_value in zip(z_query, temp_query, eta_query):
        output.append({
            "side": side,
            "station_X_over_Cax": station,
            "signed_station_X_over_Cax": -station if side == "pressure" else station,
            "station_tolerance": tolerance,
            "interpolation_method": "linear scattered wall-face interpolation; nearest fallback outside convex hull",
            "Z_over_D": float(z_value),
            "Taw_K": float(temp_value),
            "eta": float(eta_value),
            "source_face_count": len(selected),
        })
    return output


def write_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fluent_report_mass_flow(solver, zone_names: list[str]) -> dict[str, Any]:
    """Mass-flow report through Fluent report definitions."""
    out: dict[str, Any] = {"available": False, "zones": {}, "errors": []}
    rd = solver.settings.solution.report_definitions
    report_names = []
    for zone in zone_names:
        report_name = f"bofm_mdot_{zone}"
        try:
            if report_name not in list(rd.flux.keys()):
                rd.flux.create(report_name)
            rd.flux[report_name].set_state({
                "report_type": "flux-massflow",
                "boundaries": [zone],
                "per_zone": False,
            })
            report_names.append(report_name)
        except Exception as exc:
            out["errors"].append({"zone": zone, "error": str(exc)})
    if not report_names:
        return out
    try:
        results = rd.compute(report_defs=report_names) or []
        flat = {}
        for item in results:
            if isinstance(item, dict):
                flat.update(item)
        for zone in zone_names:
            report_name = f"bofm_mdot_{zone}"
            val = flat.get(report_name)
            if isinstance(val, (list, tuple)) and val:
                out["zones"][zone] = {"mass_flow_kg_s": float(val[0]), "raw": val}
            elif val is not None:
                out["zones"][zone] = {"raw": val}
        out["available"] = bool(out["zones"])
    except Exception as exc:
        out["errors"].append({"compute": str(exc)})
    return out


def coolant_mass_flow_targets(sim_case: dict[str, Any]) -> dict[str, Any]:
    zones = {}
    total = 0.0
    for zone, region in ZONE_MAP.items():
        data = sim_case.get("coolant", {}).get(region, {})
        target = data.get("periodic_14p85mm_mass_flow_kg_s")
        if target is None:
            continue
        target = float(target)
        zones[zone] = {"region": region, "target_kg_s": target}
        total += target
    return {"total_target_kg_s": total, "zones": zones}


def mass_flow_constraints(mass_flow: dict[str, Any]) -> dict[str, Any]:
    zones = mass_flow.get("zones", {})
    targets = mass_flow.get("reference_targets", {}).get("zones", {})
    coolant_actual = 0.0
    coolant_target = 0.0
    coolant_zones = {}
    for zone in ("qian", "ss", "ps"):
        actual = zones.get(zone, {}).get("mass_flow_kg_s")
        target = targets.get(zone, {}).get("target_kg_s")
        if actual is not None:
            coolant_actual += float(actual)
        if target is not None:
            coolant_target += float(target)
        coolant_zones[zone] = {
            "actual_kg_s": actual,
            "target_kg_s": target,
            "actual_over_target": None if actual is None or not target else float(actual) / float(target),
        }
    all_actual = [
        float(v["mass_flow_kg_s"])
        for v in zones.values()
        if isinstance(v, dict) and v.get("mass_flow_kg_s") is not None
    ]
    return {
        "coolant_actual_kg_s": coolant_actual,
        "coolant_target_kg_s": coolant_target,
        "coolant_mass_flow_ratio": None if coolant_target == 0 else coolant_actual / coolant_target,
        "mass_imbalance_kg_s": None if not all_actual else sum(all_actual),
        "zones": coolant_zones,
    }


def pressure_loss_diagnostic(pressure_summary: dict[str, Any]) -> dict[str, Any] | None:
    total = pressure_summary.get("fields", {}).get("total-pressure")
    if not total:
        return None
    by_surface = {row.get("surface"): row for row in total.get("surfaces", [])}
    inlet = by_surface.get("inlet")
    outlet = by_surface.get("outlet")
    if not inlet or not outlet:
        return None
    inlet_mean = float(inlet["mean"])
    outlet_mean = float(outlet["mean"])
    return {
        "definition": "diagnostic_delta_p0 = mean(total-pressure on inlet) - mean(total-pressure on outlet)",
        "delta_total_pressure_Pa": inlet_mean - outlet_mean,
        "inlet_total_pressure_mean_Pa": inlet_mean,
        "outlet_total_pressure_mean_Pa": outlet_mean,
        "note": "Diagnostic only; final loss coefficient definition must be fixed before publication.",
    }


def coolant_pressure_diagnostic(
    pressure_summary: dict[str, Any], sim_case: dict[str, Any], inlet_total_pressure_pa: float,
) -> dict[str, Any] | None:
    total = pressure_summary.get("fields", {}).get("total-pressure")
    if not total:
        return None
    by_surface = {row.get("surface"): row for row in total.get("surfaces", [])}
    zones = {}
    for zone, region in ZONE_MAP.items():
        row = by_surface.get(zone)
        if not row:
            continue
        target = inlet_total_pressure_pa * float(sim_case["coolant"][region]["pc_over_pt"])
        actual = float(row["mean"])
        zones[zone] = {
            "region": region,
            "required_total_pressure_mean_Pa": actual,
            "nasa_total_pressure_target_Pa": target,
            "required_over_nasa_target": actual / target,
            "error_Pa": actual - target,
        }
    return {
        "interpretation": "With measured mass flow imposed, this is the total pressure required by the modeled inlet/hole system; it is diagnostic rather than an imposed validation quantity.",
        "zones": zones,
    } if zones else None


def parse_convergence_log(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"available": False}
    text = path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "")
    warning_patterns = {
        "artificial_wall": r"artificial walls?",
        "reversed_flow": r"reversed flow",
        "divergence": r"divergence|diverged",
        "floating_point": r"floating point|FPE",
    }
    warnings = {name: len(re.findall(pattern, text, flags=re.IGNORECASE))
                for name, pattern in warning_patterns.items()}
    temperature_limit_re = re.compile(
        r"temperature limited to\s+([-+0-9.eE]+)\s+in\s+(\d+)\s+cells?"
        r"(?:\s+on zone\s+(\d+))?",
        flags=re.IGNORECASE,
    )
    temperature_limit_events = [
        {
            "limit_K": float(match.group(1)),
            "cell_count": int(match.group(2)),
            "zone_id": int(match.group(3)) if match.group(3) else None,
        }
        for match in temperature_limit_re.finditer(text)
    ]
    warnings["temperature_limited"] = len(temperature_limit_events)
    residual_rows = []
    sci = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)[eE][-+]?\d+"
    row_re = re.compile(
        rf"^\s*(\d+)\s+({sci})\s+({sci})\s+({sci})\s+({sci})\s+({sci})\s+({sci})\s+({sci})",
        flags=re.MULTILINE,
    )
    for match in row_re.finditer(text):
        residual_rows.append([int(match.group(1))] + [float(match.group(i)) for i in range(2, 9)])
    out: dict[str, Any] = {
        "available": True,
        "path": str(path),
        "warnings": warnings,
        "residual_row_count": len(residual_rows),
    }
    if temperature_limit_events:
        by_limit: dict[str, dict[str, Any]] = {}
        for event in temperature_limit_events:
            key = f'{event["limit_K"]:.12g}'
            row = by_limit.setdefault(
                key,
                {"limit_K": event["limit_K"], "event_count": 0, "max_cell_count": 0},
            )
            row["event_count"] += 1
            row["max_cell_count"] = max(row["max_cell_count"], event["cell_count"])
            row["last_cell_count"] = event["cell_count"]
            row["last_zone_id"] = event["zone_id"]
        out["temperature_limits"] = {
            "event_count": len(temperature_limit_events),
            "by_limit": list(by_limit.values()),
            "last_event": temperature_limit_events[-1],
        }
    if residual_rows:
        last = residual_rows[-1]
        out["last_residual_row"] = {
            "iteration": last[0],
            "continuity": last[1],
            "x_velocity": last[2],
            "y_velocity": last[3],
            "z_velocity": last[4],
            "energy": last[5],
            "k": last[6],
            "omega": last[7],
        }
    return out


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--cases-yaml", default=str(root / "configs" / "c3x_simulation_cases.yaml"))
    ap.add_argument("--simulation-case", default="nasa_44344_validation")
    ap.add_argument("--wall-pattern", action="append", default=None,
                    help="Wall glob to include; defaults to vane_wall, fallback all walls")
    ap.add_argument("--log", default=None, help="Optional Fluent iteration log to parse")
    ap.add_argument("--cores", type=int, default=2)
    ap.add_argument("--precision", choices=("single", "double"), default="single")
    ap.add_argument("--profile-csv", default=str(root / "configs" / "c3x_coordinates.csv"))
    ap.add_argument("--uv-transform-json", default=str(root / "configs" / "c3x_uvframe_film_rows.json"))
    ap.add_argument("--axial-chord-mm", type=float, default=78.16)
    ap.add_argument("--hole-diameter-mm", type=float, default=0.99)
    ap.add_argument("--span-mid-mm", type=float, default=7.425)
    ap.add_argument("--station-tolerance", type=float, default=0.01,
                    help="Half-width in X/Cax used for Kumar lateral-profile sampling")
    ap.add_argument("--profile-bins", type=int, default=61)
    ap.add_argument("--protected-pressure-xmin", type=float,
                    default=DEFAULT_PROTECTED_XMIN["pressure"])
    ap.add_argument("--protected-suction-xmin", type=float,
                    default=DEFAULT_PROTECTED_XMIN["suction"])
    ap.add_argument(
        "--nasa-pressure-reference",
        default=str(root / "configs" / "validation" / "nasa_cr182133_table_vii_surface_pressure.csv"),
    )
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    sim_case = load_case_config(Path(args.cases_yaml), args.simulation_case)
    wall_doc = sim_case.get("walls", {})
    wall_mode = str(
        wall_doc.get("thermal_mode", wall_doc.get("optimization_mode", "adiabatic"))
    ).lower()
    tg_ref = float(sim_case["mainstream"]["inlet_total_temperature_K"])
    tc_ref_doc = coolant_reference_temperature(sim_case)
    tc_ref = float(tc_ref_doc["value_K"])
    patterns = args.wall_pattern or DEFAULT_WALL_PATTERNS

    log_path = out_dir / "export_workbench_film_results.log"
    logf = log_path.open("w", encoding="utf-8")

    def log(*items):
        msg = " ".join(str(x) for x in items)
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    solver = None
    try:
        solver = F.launch(mode="solver", processor_count=args.cores, ui_mode="no_gui",
                          precision=args.precision)
        log("version:", solver.get_fluent_version())
        solver.tui.file.read_case(F.tui_path(Path(args.case).resolve()))
        solver.tui.file.read_data(F.tui_path(Path(args.data).resolve()))
        log("read case/data")

        all_walls = wall_surfaces(solver)
        walls = select_walls(all_walls, patterns)
        fields = available_fields(solver, WALL_FIELDS)
        log("wall surfaces selected:", sorted(walls))
        log("fields:", fields)

        summaries = {}
        for field in fields:
            summary = scalar_summary_on_surfaces(solver, walls, field)
            if summary is not None:
                summaries[field] = summary
                stem = field.replace("-", "_")
                path = out_dir / f"{stem}_summary.json"
                path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                write_csv_rows(out_dir / f"{stem}_surfaces.csv", summary.get("surfaces", []))
                if field == "y-plus":
                    (out_dir / "wall_yplus_summary.json").write_text(
                        json.dumps(summary, indent=2), encoding="utf-8")
                    write_csv_rows(out_dir / "wall_yplus_surfaces.csv", summary.get("surfaces", []))
                log("wrote:", path)

        heat_transfer = {
            "wall_thermal_mode": wall_mode,
            "prescribed_wall_temperature_K": wall_doc.get("temperature_K"),
            "available_fields": [],
            "fields": {},
            "face_files": {},
            "note": (
                "For paired FC/NFC runs with identical Tg and Tw, "
                "SNR = 1 - q_FC/q_NFC. This avoids dependence on Fluent "
                "reference-value normalization."
            ),
        }
        for field in available_fields(solver, HEAT_TRANSFER_FIELDS):
            summary = scalar_summary_on_surfaces(solver, walls, field)
            if summary is None:
                continue
            heat_transfer["available_fields"].append(field)
            heat_transfer["fields"][field] = summary
            try:
                heat_rows = surface_scalar_face_rows(
                    solver, walls, field, field.replace("-", "_")
                )
                annotate_kumar_coordinates(
                    heat_rows,
                    profile_csv=Path(args.profile_csv),
                    uv_transform_json=Path(args.uv_transform_json),
                    axial_chord_mm=args.axial_chord_mm,
                    hole_diameter_mm=args.hole_diameter_mm,
                    span_mid_mm=args.span_mid_mm,
                )
                heat_path = out_dir / (
                    "heat_transfer_" + field.replace("-", "_") + "_surface_faces.csv"
                )
                write_csv_rows(heat_path, heat_rows)
                heat_transfer["face_files"][field] = heat_path.name
                log("heat-transfer faces:", field, len(heat_rows), "->", heat_path)
            except Exception as exc:
                heat_transfer["face_files"][field] = {"error": repr(exc)}
                log("heat-transfer face export skipped:", field, repr(exc))
        (out_dir / "wall_heat_transfer_summary.json").write_text(
            json.dumps(heat_transfer, indent=2), encoding="utf-8"
        )

        pressure_surfaces = select_named_surfaces(
            solver, ["inlet", "outlet", "qian", "ss", "ps"]
        )
        pressure_fields = available_fields(solver, PRESSURE_FIELDS)
        pressure_summary = {
            "surfaces": sorted(pressure_surfaces),
            "available_fields": pressure_fields,
            "fields": {},
            "note": "Use these summaries for diagnostics; finalize pressure-loss definition before publication.",
        }
        for field in pressure_fields:
            summary = scalar_summary_on_surfaces(solver, pressure_surfaces, field)
            if summary is not None:
                pressure_summary["fields"][field] = summary
        pressure_loss = pressure_loss_diagnostic(pressure_summary)
        pressure_summary["pressure_loss_diagnostic"] = pressure_loss
        inlet_total_pressure = float(sim_case["mainstream"]["inlet_total_pressure_Pa"])
        pressure_summary["coolant_pressure_diagnostic"] = coolant_pressure_diagnostic(
            pressure_summary, sim_case, inlet_total_pressure,
        )
        (out_dir / "pressure_summary.json").write_text(
            json.dumps(pressure_summary, indent=2), encoding="utf-8")

        temp_summary = summaries.get("wall-temperature") or summaries.get("temperature")
        eta = None
        protected_eta = None
        if temp_summary is not None and wall_mode == "adiabatic":
            temp_field = str(temp_summary["field"])
            face_rows = wall_face_rows(solver, walls, temp_field, tg_ref, tc_ref)
            annotate_kumar_coordinates(
                face_rows,
                profile_csv=Path(args.profile_csv),
                uv_transform_json=Path(args.uv_transform_json),
                axial_chord_mm=args.axial_chord_mm,
                hole_diameter_mm=args.hole_diameter_mm,
                span_mid_mm=args.span_mid_mm,
            )
            write_csv_rows(out_dir / "eta_surface_faces.csv", face_rows)
            eta = eta_summary(face_rows, tg_ref, tc_ref)
            protected_eta = protected_eta_summary(
                face_rows,
                tg_ref,
                tc_ref,
                pressure_xmin=args.protected_pressure_xmin,
                suction_xmin=args.protected_suction_xmin,
            )
            (out_dir / "wall_eta_summary.json").write_text(
                json.dumps(eta, indent=2), encoding="utf-8")
            (out_dir / "wall_eta_protected_summary.json").write_text(
                json.dumps(protected_eta, indent=2), encoding="utf-8")
            write_csv_rows(out_dir / "wall_eta_surfaces.csv", eta["surfaces"])
            ps_profile = lateral_eta_profile(
                face_rows, "pressure", 0.31, args.station_tolerance, args.profile_bins
            )
            ss_profile = lateral_eta_profile(
                face_rows, "suction", 0.48, args.station_tolerance, args.profile_bins
            )
            write_csv_rows(out_dir / "eta_lateral_ps_xcax_0p31.csv", ps_profile)
            write_csv_rows(out_dir / "eta_lateral_ss_xcax_0p48.csv", ss_profile)
            eta["lateral_profiles"] = {
                "pressure_X_over_Cax_0p31": {
                    "rows": len(ps_profile),
                    "path": "eta_lateral_ps_xcax_0p31.csv",
                    "tolerance": args.station_tolerance,
                },
                "suction_X_over_Cax_0p48": {
                    "rows": len(ss_profile),
                    "path": "eta_lateral_ss_xcax_0p48.csv",
                    "tolerance": args.station_tolerance,
                },
            }
            (out_dir / "wall_eta_summary.json").write_text(
                json.dumps(eta, indent=2), encoding="utf-8")
            log("eta_bar:", eta["eta_bar"])
            log("protected_eta_bar:", protected_eta["eta_bar"])
            log("Kumar profile rows: pressure=", len(ps_profile), "suction=", len(ss_profile))

            if "pressure" in pressure_fields and Path(args.nasa_pressure_reference).is_file():
                pressure_face_rows = surface_scalar_face_rows(
                    solver, walls, "pressure", "static_pressure_Pa"
                )
                annotate_kumar_coordinates(
                    pressure_face_rows,
                    profile_csv=Path(args.profile_csv),
                    uv_transform_json=Path(args.uv_transform_json),
                    axial_chord_mm=args.axial_chord_mm,
                    hole_diameter_mm=args.hole_diameter_mm,
                    span_mid_mm=args.span_mid_mm,
                )
                nasa_rows, nasa_summary = compare_nasa_surface_pressure(
                    pressure_face_rows,
                    Path(args.nasa_pressure_reference),
                    inlet_total_pressure,
                )
                write_csv_rows(out_dir / "nasa_surface_pressure_comparison.csv", nasa_rows)
                (out_dir / "nasa_surface_pressure_summary.json").write_text(
                    json.dumps(nasa_summary, indent=2), encoding="utf-8"
                )
                log("NASA surface-pressure RMSE:", nasa_summary["rmse"])
        elif temp_summary is not None:
            log("eta export skipped for non-adiabatic wall mode:", wall_mode)

        mass_flow = fluent_report_mass_flow(solver, ["inlet", "outlet", "qian", "ss", "ps"])
        mass_flow["reference_targets"] = coolant_mass_flow_targets(sim_case)
        mass_constraints = mass_flow_constraints(mass_flow)
        mass_flow["constraints"] = mass_constraints
        (out_dir / "mass_flow_summary.json").write_text(json.dumps(mass_flow, indent=2), encoding="utf-8")
        convergence = parse_convergence_log(Path(args.log) if args.log else None)
        (out_dir / "convergence_summary.json").write_text(
            json.dumps(convergence, indent=2), encoding="utf-8")

        yplus = summaries.get("y-plus")
        valid = bool(eta is not None or heat_transfer["face_files"])
        bo_summary = {
            "valid": valid,
            "simulation_case": args.simulation_case,
            "wall_thermal_mode": wall_mode,
            "objective": {
                "eta_bar": None if eta is None else eta["eta_bar"],
                "protected_eta_bar": (
                    None if protected_eta is None else protected_eta["eta_bar"]
                ),
                "protected_area_m2": (
                    None if protected_eta is None else protected_eta["area_m2"]
                ),
            },
            "constraints": {
                "coolant_mass_flow_ratio": mass_constraints["coolant_mass_flow_ratio"],
                "coolant_actual_kg_s": mass_constraints["coolant_actual_kg_s"],
                "mass_imbalance": mass_constraints["mass_imbalance_kg_s"],
                "pressure_loss": pressure_loss,
                "y_plus_p95": None if yplus is None else yplus["p95"],
                "y_plus_max": None if yplus is None else yplus["max"],
            },
            "references": {
                "Tg_ref_K": tg_ref,
                "Tc_ref": tc_ref_doc,
            },
            "diagnostics": {
                "selected_wall_surfaces": sorted(walls),
                "all_wall_surfaces": sorted(all_walls),
                "available_scalar_fields": fields,
                "available_heat_transfer_fields": heat_transfer["available_fields"],
                "mass_flow_report_available": mass_flow["available"],
                "convergence": convergence,
                "export_log": str(log_path),
            },
        }
        (out_dir / "bo_summary.json").write_text(json.dumps(bo_summary, indent=2), encoding="utf-8")
        log("wrote:", out_dir / "bo_summary.json")
        log("DONE_OK")
        return 0
    except Exception as exc:
        failure = {"valid": False, "error": repr(exc)}
        (out_dir / "bo_summary.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        log("EXCEPTION:", repr(exc))
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
