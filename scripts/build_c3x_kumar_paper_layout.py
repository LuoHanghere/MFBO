"""Extract and build the Kumar et al. C3X film-hole marker layout.

The 2023 paper delegates the vane and baseline hole geometry to Hylton et al.
(NASA CR-182133). This script therefore uses the NASA Table II profile,
Table III surface arcs, and Table IV hole geometry, then applies the six angle
and forward/reverse cases from Kumar et al. Table 1.

No U/V-frame fit or figure digitization is used for the downstream rows.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from bofm.geometry import parametrization as P
from bofm.geometry.external_flow import build_airfoil_external_domain
from bofm.geometry.film_topology import point_in_poly_xy
from bofm.geometry.profile import densify_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_CSV = ROOT / "configs" / "c3x_coordinates.csv"

NASA_SUCTION_ARC_MM = 180.37
NASA_PRESSURE_ARC_MM = 139.82
DIAMETER_MM = 0.99
HOLE_LENGTH_MM = 3.35
P_OVER_D = 4.0
S_OVER_D = 3.0
LE_S_OVER_D = 7.5
COMMON_PERIOD_D = 15.0
PASSAGE_OVERLAP_D = 3.0
INNER_OVERLAP_D = 3.0
LE_PASSAGE_OVERLAP_D = 0.5
LE_INNER_OVERLAP_D = 0.0
LE_RADIAL_ANGLE_DEG = 90.0
LE_BASE_Z_MM = 2.8

PAPER_CASES = {
    1: {"pressure_angle_deg": 30.0, "suction_angle_deg": 35.0, "orientation": "forward"},
    2: {"pressure_angle_deg": 30.0, "suction_angle_deg": 35.0, "orientation": "reverse"},
    3: {"pressure_angle_deg": 45.0, "suction_angle_deg": 50.0, "orientation": "forward"},
    4: {"pressure_angle_deg": 45.0, "suction_angle_deg": 50.0, "orientation": "reverse"},
    5: {"pressure_angle_deg": 60.0, "suction_angle_deg": 75.0, "orientation": "forward"},
    6: {"pressure_angle_deg": 60.0, "suction_angle_deg": 75.0, "orientation": "reverse"},
}


@dataclass
class PaperSurface:
    name: str
    xy: np.ndarray
    arc: np.ndarray
    reference_arc_mm: float

    @property
    def computed_arc_mm(self) -> float:
        return float(self.arc[-1])

    def locate_reference_arc(self, s_reference_mm: float) -> tuple[np.ndarray, np.ndarray]:
        s_model = s_reference_mm * self.computed_arc_mm / self.reference_arc_mm
        x = float(np.interp(s_model, self.arc, self.xy[:, 0]))
        y = float(np.interp(s_model, self.arc, self.xy[:, 1]))
        ds = 0.10
        p0 = np.array([
            np.interp(max(0.0, s_model - ds), self.arc, self.xy[:, 0]),
            np.interp(max(0.0, s_model - ds), self.arc, self.xy[:, 1]),
        ])
        p1 = np.array([
            np.interp(min(self.computed_arc_mm, s_model + ds), self.arc, self.xy[:, 0]),
            np.interp(min(self.computed_arc_mm, s_model + ds), self.arc, self.xy[:, 1]),
        ])
        tangent = p1 - p0
        tangent /= np.linalg.norm(tangent)
        return np.array([x, y]), tangent


def cumulative_arc(xy: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))])


def interpolate_split(xy: np.ndarray, arc: np.ndarray, target: float) -> tuple[np.ndarray, int]:
    i = int(np.searchsorted(arc, target))
    i = min(max(i, 1), len(xy) - 1)
    f = (target - arc[i - 1]) / (arc[i] - arc[i - 1])
    return xy[i - 1] + f * (xy[i] - xy[i - 1]), i


def resample_by_arc(xy: np.ndarray, count: int) -> np.ndarray:
    arc = cumulative_arc(xy)
    targets = np.linspace(0.0, arc[-1], count)
    return np.column_stack([
        np.interp(targets, arc, xy[:, 0]),
        np.interp(targets, arc, xy[:, 1]),
    ])


def build_paper_surfaces() -> tuple[dict[str, PaperSurface], np.ndarray, dict]:
    raw = P.load_profile(PROFILE_CSV)
    if abs(float(raw[28, 1]) - 0.411) > 1.0e-9:
        raise ValueError("NASA Table II point 29 must be y=0.411 mm")

    # The Table II point with minimum axial x is not the Table III geometric
    # stagnation split. Move the split along the short branch until the two
    # computed surface arcs jointly match Table III.
    dense = densify_profile(raw, n_per_surface=2000, cluster=0.5)
    base = P.build_surfaces(dense)
    suction0 = np.asarray(base["suction"].xy, dtype=float)
    pressure0 = np.asarray(base["pressure"].xy, dtype=float)
    suction0_arc = cumulative_arc(suction0)
    pressure0_arc = cumulative_arc(pressure0)
    split_shift_mm = 0.5 * (
        (NASA_SUCTION_ARC_MM - suction0_arc[-1])
        + (pressure0_arc[-1] - NASA_PRESSURE_ARC_MM)
    )
    stagnation, split_i = interpolate_split(pressure0, pressure0_arc, split_shift_mm)

    suction_xy = np.vstack([stagnation, pressure0[split_i - 1::-1], suction0[1:]])
    pressure_xy = np.vstack([stagnation, pressure0[split_i:]])
    suction = PaperSurface("suction", suction_xy, cumulative_arc(suction_xy), NASA_SUCTION_ARC_MM)
    pressure = PaperSurface("pressure", pressure_xy, cumulative_arc(pressure_xy), NASA_PRESSURE_ARC_MM)

    arc_error = {
        "suction_mm": suction.computed_arc_mm - NASA_SUCTION_ARC_MM,
        "pressure_mm": pressure.computed_arc_mm - NASA_PRESSURE_ARC_MM,
    }
    if max(abs(v) for v in arc_error.values()) > 0.05:
        raise ValueError("Table III surface-arc reconstruction exceeds 0.05 mm")

    suction_model = resample_by_arc(suction_xy, 260)
    pressure_model = resample_by_arc(pressure_xy, 220)
    profile_model = np.vstack([suction_model, pressure_model[::-1][1:-1]])
    meta = {
        "geometric_stagnation_xy_mm": stagnation.tolist(),
        "split_shift_from_min_x_mm": float(split_shift_mm),
        "computed_surface_arcs_mm": {
            "suction": suction.computed_arc_mm,
            "pressure": pressure.computed_arc_mm,
        },
        "surface_arc_errors_vs_table_iii_mm": arc_error,
    }
    return {"suction": suction, "pressure": pressure}, profile_model, meta


def outward_normal(point: np.ndarray, tangent: np.ndarray, profile: np.ndarray) -> np.ndarray:
    n = np.array([-tangent[1], tangent[0]], dtype=float)
    eps = 0.10
    plus_inside = point_in_poly_xy(point + eps * n, profile)
    minus_inside = point_in_poly_xy(point - eps * n, profile)
    if plus_inside and not minus_inside:
        n = -n
    elif plus_inside == minus_inside:
        centroid = np.mean(profile, axis=0)
        if float(np.dot(n, point - centroid)) < 0.0:
            n = -n
    return n / np.linalg.norm(n)


def selected_case(args: argparse.Namespace) -> dict:
    case = dict(PAPER_CASES[args.case_id])
    if args.pressure_angle_deg is not None:
        case["pressure_angle_deg"] = float(args.pressure_angle_deg)
    if args.suction_angle_deg is not None:
        case["suction_angle_deg"] = float(args.suction_angle_deg)
    if args.orientation is not None:
        case["orientation"] = args.orientation
    case["case_id"] = int(args.case_id)
    case["custom_override"] = any(
        value is not None
        for value in (args.pressure_angle_deg, args.suction_angle_deg, args.orientation)
    )
    return case


def build_rows(
    surfaces: dict[str, PaperSurface], profile: np.ndarray, case: dict, span_mm: float
) -> list[dict]:
    row_defs = [
        ("SS1", "suction", 12, 0.252, -1.0),
        ("SS2", "suction", 11, 0.252, +1.0),
        ("PS1", "pressure", 18, 0.225, -1.0),
        ("PS2", "pressure", 19, 0.225, +1.0),
    ]
    shared_frames = {}
    stream_sign = 1.0 if case["orientation"] == "forward" else -1.0
    for surface_name, center_fraction in (("suction", 0.252), ("pressure", 0.225)):
        surface = surfaces[surface_name]
        center_s = center_fraction * surface.reference_arc_mm
        center_point, center_tangent = surface.locate_reference_arc(center_s)
        center_normal = outward_normal(center_point, center_tangent, profile)
        angle = float(case[f"{surface_name}_angle_deg"])
        alpha = math.radians(angle)
        exit_axis = stream_sign * math.cos(alpha) * center_tangent + math.sin(alpha) * center_normal
        exit_axis /= np.linalg.norm(exit_axis)
        shared_frames[surface_name] = {
            "center_surface_arc_reference_mm": float(center_s),
            "center_xy_mm": center_point.tolist(),
            "tangent_le_to_te": center_tangent.tolist(),
            "outward_normal_xy": center_normal.tolist(),
            "coolant_exit_axis_xy": exit_axis.tolist(),
        }

    rows = []
    for row_id, surface_name, nasa_hole, center_fraction, side in row_defs:
        surface = surfaces[surface_name]
        s_ref = center_fraction * surface.reference_arc_mm + side * 0.5 * P_OVER_D * DIAMETER_MM
        point, tangent = surface.locate_reference_arc(s_ref)
        n_out = outward_normal(point, tangent, profile)
        angle = float(case[f"{surface_name}_angle_deg"])
        exit_axis = np.asarray(shared_frames[surface_name]["coolant_exit_axis_xy"], dtype=float)
        into_axis = -exit_axis

        outside_probe = point + 0.20 * DIAMETER_MM * exit_axis
        inside_probe = point + 0.20 * DIAMETER_MM * into_axis
        outside_ok = not point_in_poly_xy(outside_probe, profile)
        inside_ok = point_in_poly_xy(inside_probe, profile)
        if not (outside_ok and inside_ok):
            raise ValueError(f"{row_id} axis does not cross from blade to passage correctly")

        marker_start_xy = point + PASSAGE_OVERLAP_D * DIAMETER_MM * exit_axis
        marker_end_xy = point + (HOLE_LENGTH_MM + INNER_OVERLAP_D * DIAMETER_MM) * into_axis
        span_pitch = S_OVER_D * DIAMETER_MM
        span_positions = np.arange(0.5 * span_pitch, span_mm, span_pitch)
        cylinder_markers = []
        for z_index, z in enumerate(span_positions, 1):
            cylinder_markers.append({
                "id": "%s_z%02d" % (row_id, z_index),
                "start_mm": [float(marker_start_xy[0]), float(marker_start_xy[1]), float(z)],
                "end_mm": [float(marker_end_xy[0]), float(marker_end_xy[1]), float(z)],
                "radius_mm": 0.5 * DIAMETER_MM,
                "radius_vector_mm": [0.0, 0.0, 0.5 * DIAMETER_MM],
                "radius_point_mm": [
                    float(marker_end_xy[0]), float(marker_end_xy[1]), float(z + 0.5 * DIAMETER_MM)
                ],
            })
        rows.append({
            "row_id": row_id,
            "surface": surface_name,
            "source_nasa_hole": nasa_hole,
            "surface_arc_reference_mm": float(s_ref),
            "s_over_s0": float(s_ref / surface.reference_arc_mm),
            "surface_xy_mm": point.tolist(),
            "surface_tangent_le_to_te": tangent.tolist(),
            "surface_tangent_angle_deg": float(math.degrees(math.atan2(tangent[1], tangent[0]))),
            "outward_normal_xy": n_out.tolist(),
            "streamwise_injection_angle_deg": angle,
            "orientation": case["orientation"],
            "coolant_exit_axis_xy": exit_axis.tolist(),
            "surface_to_plenum_axis_xy": into_axis.tolist(),
            "shared_pair_frame": shared_frames[surface_name],
            "direction_checks": {"outside_probe_in_passage": outside_ok, "inside_probe_in_blade": inside_ok},
            "diameter_mm": DIAMETER_MM,
            "physical_hole_length_mm": HOLE_LENGTH_MM,
            "p_over_D": P_OVER_D,
            "s_over_D": S_OVER_D,
            "span_pitch_mm": span_pitch,
            "span_positions_mm": span_positions.tolist(),
            "cylinder_markers": cylinder_markers,
        })
    return rows


def build_leading_edge_rows(
    surfaces: dict[str, PaperSurface], profile: np.ndarray, span_mm: float
) -> list[dict]:
    row_pitch = P_OVER_D * DIAMETER_MM
    span_pitch = LE_S_OVER_D * DIAMETER_MM
    row_defs = [
        ("LE1", "pressure", 17, -2.0 * row_pitch),
        ("LE2", "pressure", 16, -1.0 * row_pitch),
        ("LE3", "stagnation", 15, 0.0),
        ("LE4", "suction", 14, +1.0 * row_pitch),
        ("LE5", "suction", 13, +2.0 * row_pitch),
    ]
    rows = []
    for row_index, (row_id, surface_name, nasa_hole, signed_arc) in enumerate(row_defs):
        if signed_arc < 0.0:
            point, tangent = surfaces["pressure"].locate_reference_arc(abs(signed_arc))
            n_out = outward_normal(point, tangent, profile)
        elif signed_arc > 0.0:
            point, tangent = surfaces["suction"].locate_reference_arc(signed_arc)
            n_out = outward_normal(point, tangent, profile)
        else:
            point = np.asarray(surfaces["suction"].xy[0], dtype=float)
            p_ss, t_ss = surfaces["suction"].locate_reference_arc(0.25 * DIAMETER_MM)
            p_ps, t_ps = surfaces["pressure"].locate_reference_arc(0.25 * DIAMETER_MM)
            n_ss = outward_normal(p_ss, t_ss, profile)
            n_ps = outward_normal(p_ps, t_ps, profile)
            n_out = n_ss + n_ps
            n_out /= np.linalg.norm(n_out)
            tangent = np.array([n_out[1], -n_out[0]], dtype=float)

        exit_axis = np.array([n_out[0], n_out[1], 0.0])
        exit_axis /= np.linalg.norm(exit_axis)
        into_axis = -exit_axis
        radius_vector = np.array([tangent[0], tangent[1], 0.0], dtype=float)
        radius_vector -= np.dot(radius_vector, exit_axis) * exit_axis
        radius_vector *= (0.5 * DIAMETER_MM) / np.linalg.norm(radius_vector)

        outside_probe = point + 0.20 * DIAMETER_MM * exit_axis[:2]
        inside_probe = point + 0.20 * DIAMETER_MM * into_axis[:2]
        outside_ok = not point_in_poly_xy(outside_probe, profile)
        inside_ok = point_in_poly_xy(inside_probe, profile)
        if not (outside_ok and inside_ok):
            raise ValueError(f"{row_id} axis does not cross from blade to passage correctly")

        phase = LE_BASE_Z_MM + (0.5 * span_pitch if row_index % 2 else 0.0)
        span_positions = np.arange(phase, span_mm, span_pitch)
        if len(span_positions) != 2:
            raise ValueError(f"{row_id} must contain two holes in the 15D periodic span")

        cylinder_markers = []
        for z_index, z in enumerate(span_positions, 1):
            surface_point = np.array([point[0], point[1], z], dtype=float)
            start = surface_point + LE_PASSAGE_OVERLAP_D * DIAMETER_MM * exit_axis
            end = surface_point + (HOLE_LENGTH_MM + LE_INNER_OVERLAP_D * DIAMETER_MM) * into_axis
            radius_point = end + radius_vector
            cylinder_markers.append({
                "id": "%s_NASA%02d_z%02d" % (row_id, nasa_hole, z_index),
                "surface_point_mm": surface_point.tolist(),
                "start_mm": start.tolist(),
                "end_mm": end.tolist(),
                "radius_mm": 0.5 * DIAMETER_MM,
                "radius_vector_mm": radius_vector.tolist(),
                "radius_point_mm": radius_point.tolist(),
            })

        rows.append({
            "row_id": row_id,
            "surface": surface_name,
            "source_nasa_hole": nasa_hole,
            "signed_surface_arc_from_stagnation_mm": float(signed_arc),
            "surface_xy_mm": point.tolist(),
            "surface_tangent_le_to_te": tangent.tolist(),
            "outward_normal_xy": n_out.tolist(),
            "radial_injection_angle_deg": LE_RADIAL_ANGLE_DEG,
            "axis_plane": "XY",
            "coolant_exit_axis_xyz": exit_axis.tolist(),
            "surface_to_plenum_axis_xyz": into_axis.tolist(),
            "direction_checks": {"outside_probe_in_passage": outside_ok, "inside_probe_in_blade": inside_ok},
            "diameter_mm": DIAMETER_MM,
            "physical_hole_length_mm": HOLE_LENGTH_MM,
            "p_over_D": P_OVER_D,
            "s_over_D": LE_S_OVER_D,
            "span_pitch_mm": span_pitch,
            "span_phase_mm": float(phase),
            "span_positions_mm": span_positions.tolist(),
            "stagger_group": "A" if row_index % 2 == 0 else "B",
            "cylinder_markers": cylinder_markers,
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "hole_id", "row_id", "surface", "source_nasa_hole", "surface_arc_reference_mm", "s_over_s0",
        "x_mm", "y_mm", "z_mm", "tangent_angle_deg", "injection_angle_deg", "orientation",
        "exit_axis_x", "exit_axis_y", "into_axis_x", "into_axis_y", "diameter_mm",
        "physical_hole_length_mm", "span_pitch_mm",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for marker in row["cylinder_markers"]:
                writer.writerow({
                "hole_id": marker["id"],
                "row_id": row["row_id"],
                "surface": row["surface"],
                "source_nasa_hole": row["source_nasa_hole"],
                "surface_arc_reference_mm": f'{row["surface_arc_reference_mm"]:.6f}',
                "s_over_s0": f'{row["s_over_s0"]:.9f}',
                "x_mm": f'{row["surface_xy_mm"][0]:.6f}',
                "y_mm": f'{row["surface_xy_mm"][1]:.6f}',
                "z_mm": f'{marker["start_mm"][2]:.6f}',
                "tangent_angle_deg": f'{row["surface_tangent_angle_deg"]:.6f}',
                "injection_angle_deg": f'{row["streamwise_injection_angle_deg"]:.6f}',
                "orientation": row["orientation"],
                "exit_axis_x": f'{row["coolant_exit_axis_xy"][0]:.9f}',
                "exit_axis_y": f'{row["coolant_exit_axis_xy"][1]:.9f}',
                "into_axis_x": f'{row["surface_to_plenum_axis_xy"][0]:.9f}',
                "into_axis_y": f'{row["surface_to_plenum_axis_xy"][1]:.9f}',
                "diameter_mm": f'{row["diameter_mm"]:.6f}',
                "physical_hole_length_mm": f'{row["physical_hole_length_mm"]:.6f}',
                "span_pitch_mm": f'{row["span_pitch_mm"]:.6f}',
                })


def write_le_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "hole_id", "row_id", "surface", "source_nasa_hole", "signed_surface_arc_mm",
        "x_mm", "y_mm", "z_mm", "exit_axis_x", "exit_axis_y", "exit_axis_z",
        "diameter_mm", "physical_hole_length_mm", "span_pitch_mm", "stagger_group",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for marker in row["cylinder_markers"]:
                surface_point = marker["surface_point_mm"]
                exit_axis = row["coolant_exit_axis_xyz"]
                writer.writerow({
                    "hole_id": marker["id"],
                    "row_id": row["row_id"],
                    "surface": row["surface"],
                    "source_nasa_hole": row["source_nasa_hole"],
                    "signed_surface_arc_mm": f'{row["signed_surface_arc_from_stagnation_mm"]:.6f}',
                    "x_mm": f'{surface_point[0]:.6f}',
                    "y_mm": f'{surface_point[1]:.6f}',
                    "z_mm": f'{surface_point[2]:.6f}',
                    "exit_axis_x": f'{exit_axis[0]:.9f}',
                    "exit_axis_y": f'{exit_axis[1]:.9f}',
                    "exit_axis_z": f'{exit_axis[2]:.9f}',
                    "diameter_mm": f'{row["diameter_mm"]:.6f}',
                    "physical_hole_length_mm": f'{row["physical_hole_length_mm"]:.6f}',
                    "span_pitch_mm": f'{row["span_pitch_mm"]:.6f}',
                    "stagger_group": row["stagger_group"],
                })


def write_plot(
    path: Path, profile: np.ndarray, rows: list[dict], leading_edge_rows: list[dict], case: dict
) -> None:
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.fill(profile[:, 0], profile[:, 1], facecolor="0.86", edgecolor="black", lw=1.2, label="NASA C3X")
    colors = {"suction": "tab:blue", "pressure": "tab:red"}
    for row in rows:
        p = np.asarray(row["surface_xy_mm"])
        start = np.asarray(row["cylinder_markers"][0]["start_mm"][:2])
        end = np.asarray(row["cylinder_markers"][0]["end_mm"][:2])
        color = colors[row["surface"]]
        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, lw=4.0, alpha=0.72)
        ax.plot(p[0], p[1], "o", color=color, ms=7)
        exit_axis = np.asarray(row["coolant_exit_axis_xy"])
        ax.arrow(p[0], p[1], 3.0 * exit_axis[0], 3.0 * exit_axis[1],
                 width=0.05, head_width=0.55, length_includes_head=True, color=color)
        ax.annotate(
            f'{row["row_id"]}  s/s0={row["s_over_s0"]:.4f}',
            p, xytext=(6, 6), textcoords="offset points", color=color, fontsize=9,
        )
    for row in leading_edge_rows:
        p = np.asarray(row["surface_xy_mm"])
        start = np.asarray(row["cylinder_markers"][0]["start_mm"][:2])
        end = np.asarray(row["cylinder_markers"][0]["end_mm"][:2])
        ax.plot([start[0], end[0]], [start[1], end[1]], color="tab:green", lw=3.2, alpha=0.72)
        ax.plot(p[0], p[1], "o", color="tab:green", ms=6)
        ax.annotate(
            f'{row["row_id"]}/{row["source_nasa_hole"]}',
            p, xytext=(-22, 5), textcoords="offset points", color="tab:green", fontsize=8,
        )
    ax.set_aspect("equal")
    ax.set_xlim(-3, 55)
    ax.set_ylim(74, 137)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("x [mm] (NASA axial)")
    ax.set_ylabel("y [mm] (NASA tangential)")
    ax.set_title(
        "Kumar/NASA C3X film-hole markers - case %d, %s" %
        (case["case_id"], case["orientation"])
    )
    ax.text(
        0.02, 0.02,
        "PS %.0f deg | SS %.0f deg | D=%.2f mm | row P/D=%.1f\n"
        "downstream span pitch=%.2f mm | LE pitch=%.2f mm | common period=%.2f mm" % (
            case["pressure_angle_deg"], case["suction_angle_deg"], DIAMETER_MM,
            P_OVER_D, S_OVER_D * DIAMETER_MM, LE_S_OVER_D * DIAMETER_MM,
            COMMON_PERIOD_D * DIAMETER_MM,
        ),
        transform=ax.transAxes, fontsize=8.5,
        bbox={"facecolor": "white", "edgecolor": "0.7", "alpha": 0.9},
    )
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_le_stagger_plot(path: Path, rows: list[dict], span_mm: float) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for row in rows:
        s = row["signed_surface_arc_from_stagnation_mm"]
        z = row["span_positions_mm"]
        ax.scatter(z, [s] * len(z), s=70, label=f'{row["row_id"]} / NASA {row["source_nasa_hole"]}')
    ax.set_xlim(0.0, span_mm)
    ax.set_xticks(np.linspace(0.0, span_mm, 7))
    ax.set_xlabel("z [mm] in 15D periodic span")
    ax.set_ylabel("signed surface arc from stagnation [mm]")
    ax.set_title("NASA C3X leading-edge showerhead: five staggered rows")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=2, fontsize=8)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def build_external_flow_json(path: Path, surfaces: dict[str, PaperSurface], profile: np.ndarray) -> dict:
    cfg = yaml.safe_load((ROOT / "configs" / "c3x_baseline.yaml").read_text(encoding="utf-8"))
    geom = cfg["geometry"]
    passage = geom.get("passage_domain", {})
    p_surfaces = {
        name: P.Surface(name, surface.xy, surface.arc)
        for name, surface in surfaces.items()
    }
    dom = build_airfoil_external_domain(
        p_surfaces,
        pitch_mm=float(geom["pitch_mm"]),
        axial_chord_mm=float(geom["axial_chord_mm"]),
        up_chord=float(passage.get("upstream_axial_chords", 1.5)),
        down_chord=float(passage.get("downstream_axial_chords", 1.0)),
        inlet_angle_deg=0.0,
        exit_angle_deg=float(passage.get("downstream_periodic_angle_deg", -72.38)),
    )
    data = {
        "source": "Kumar et al. 2023 geometry delegated to NASA CR-182133 Tables II-III",
        "units": "mm",
        "topology": "single C3X vane cutout in a curved duct with translated periodic side walls",
        "physical_pitch_mm": float(dom.physical_pitch_mm),
        "pitch_mm": float(dom.periodic_width_mm),
        "periodic_width_mm": float(dom.periodic_width_mm),
        "periodic_translation_xy_mm": list(dom.periodic_translation_xy_mm),
        "span_mm": COMMON_PERIOD_D * DIAMETER_MM,
        "y_low": float(dom.y_low) if dom.y_low is not None else None,
        "y_high": float(dom.y_high) if dom.y_high is not None else None,
        "x_in": float(dom.x_in),
        "x_out": float(dom.x_out),
        "min_wall_clearance_mm": float(dom.min_wall_clearance_mm),
        "outer_loop_xy_mm": dom.outer_loop_xy.tolist(),
        "airfoil_xy_mm": profile.tolist(),
        "periodic_lower_xy_mm": dom.side_lower_xy.tolist(),
        "periodic_upper_xy_mm": dom.side_upper_xy.tolist(),
        "inlet_xy_mm": dom.inlet_xy.tolist(),
        "outlet_xy_mm": dom.outlet_xy.tolist(),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", type=int, choices=sorted(PAPER_CASES), default=1)
    parser.add_argument("--pressure-angle-deg", type=float)
    parser.add_argument("--suction-angle-deg", type=float)
    parser.add_argument("--orientation", choices=("forward", "reverse"))
    parser.add_argument("--out-json", default=str(ROOT / "configs" / "c3x_kumar_paper_hole_markers.json"))
    parser.add_argument("--out-csv", default=str(ROOT / "configs" / "c3x_kumar_paper_hole_markers.csv"))
    parser.add_argument("--out-png", default=str(ROOT / "configs" / "c3x_kumar_paper_hole_markers.png"))
    parser.add_argument("--out-le-csv", default=str(ROOT / "configs" / "c3x_kumar_paper_le_hole_markers.csv"))
    parser.add_argument("--out-le-png", default=str(ROOT / "configs" / "c3x_kumar_paper_le_stagger.png"))
    parser.add_argument("--external-flow-json", default=str(ROOT / "configs" / "c3x_kumar_paper_external_flow.json"))
    args = parser.parse_args()

    out_json = Path(args.out_json).resolve()
    out_csv = Path(args.out_csv).resolve()
    out_png = Path(args.out_png).resolve()
    out_le_csv = Path(args.out_le_csv).resolve()
    out_le_png = Path(args.out_le_png).resolve()
    external_json = Path(args.external_flow_json).resolve()
    for path in (out_json, out_csv, out_png, out_le_csv, out_le_png, external_json):
        path.parent.mkdir(parents=True, exist_ok=True)

    case = selected_case(args)
    surfaces, profile, reconstruction = build_paper_surfaces()
    span = COMMON_PERIOD_D * DIAMETER_MM
    rows = build_rows(surfaces, profile, case, span)
    leading_edge_rows = build_leading_edge_rows(surfaces, profile, span)
    external = build_external_flow_json(external_json, surfaces, profile)

    data = {
        "source": {
            "paper": "Kumar et al., A Numerical Study of Film Cooling on NASA-C3X Vane by Forward and Reverse Injection, 2023",
            "paper_file": "978-981-19-3379-0_28-39.pdf",
            "primary_geometry": "NASA CR-182133 Tables II-IV",
            "method": "Table III surface-arc placement; no U/V fit and no figure scaling",
        },
        "units": "mm",
        "selected_case": case,
        "paper_cases": PAPER_CASES,
        "geometry": {
            "diameter_mm": DIAMETER_MM,
            "physical_hole_length_mm": HOLE_LENGTH_MM,
            "p_over_D": P_OVER_D,
            "s_over_D": S_OVER_D,
            "leading_edge_s_over_D": LE_S_OVER_D,
            "periodic_span_mm": span,
            "downstream_span_pitch_mm": S_OVER_D * DIAMETER_MM,
            "leading_edge_span_pitch_mm": LE_S_OVER_D * DIAMETER_MM,
            "common_period_derivation": "LCM(3D downstream, 7.5D leading edge) = 15D",
            "inline_rows": True,
            "downstream_marker_passage_overlap_D": PASSAGE_OVERLAP_D,
            "downstream_marker_inner_overlap_D": INNER_OVERLAP_D,
            "downstream_marker_total_length_mm": HOLE_LENGTH_MM + (PASSAGE_OVERLAP_D + INNER_OVERLAP_D) * DIAMETER_MM,
            "leading_edge_radial_angle_deg": LE_RADIAL_ANGLE_DEG,
            "leading_edge_marker_passage_overlap_D": LE_PASSAGE_OVERLAP_D,
            "leading_edge_marker_inner_overlap_D": LE_INNER_OVERLAP_D,
            "leading_edge_stagger": "adjacent rows offset by 0.5 span pitch",
            "reference_surface_arcs_mm": {
                "suction": NASA_SUCTION_ARC_MM,
                "pressure": NASA_PRESSURE_ARC_MM,
            },
            "row_pair_centers_s_over_s0": {"suction": 0.252, "pressure": 0.225},
            "row_pair_spacing_mm": P_OVER_D * DIAMETER_MM,
            "reconstruction": reconstruction,
        },
        "external_flow_json": str(external_json),
        "external_flow_summary": {
            "physical_pitch_mm": external["physical_pitch_mm"],
            "periodic_width_mm": external["periodic_width_mm"],
            "span_mm": external["span_mm"],
            "min_wall_clearance_mm": external["min_wall_clearance_mm"],
        },
        "rows": rows,
        "leading_edge_rows": leading_edge_rows,
    }
    out_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    write_csv(out_csv, rows)
    write_le_csv(out_le_csv, leading_edge_rows)
    write_plot(out_png, profile, rows, leading_edge_rows, case)
    write_le_stagger_plot(out_le_png, leading_edge_rows, span)

    print("case:", case)
    print("stagnation:", reconstruction["geometric_stagnation_xy_mm"])
    print("surface arc errors [mm]:", reconstruction["surface_arc_errors_vs_table_iii_mm"])
    for row in rows:
        print(
            "%s s/s0=%.6f xy=(%.6f, %.6f) exit_axis=(%.6f, %.6f)" % (
                row["row_id"], row["s_over_s0"], row["surface_xy_mm"][0],
                row["surface_xy_mm"][1], row["coolant_exit_axis_xy"][0],
                row["coolant_exit_axis_xy"][1],
            )
        )
    for row in leading_edge_rows:
        print(
            "%s NASA%d signed_s=%+.3f xy=(%.6f, %.6f) z=%s" % (
                row["row_id"], row["source_nasa_hole"],
                row["signed_surface_arc_from_stagnation_mm"], row["surface_xy_mm"][0],
                row["surface_xy_mm"][1], row["span_positions_mm"],
            )
        )
    print("wrote:", out_json)
    print("wrote:", out_csv)
    print("wrote:", out_png)
    print("wrote:", out_le_csv)
    print("wrote:", out_le_png)
    print("wrote:", external_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
