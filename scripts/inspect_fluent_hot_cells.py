"""Locate temperature-limited Fluent cells directly from case/data HDF5 files.

The Fluent data array is indexed by the single cell-zone ID range stored in the
case file.  For each selected cell this script reconstructs its incident faces
and vertices, then reports a vertex-mean location and a bounding box.  The
vertex mean is a diagnostic location, not Fluent's volume-weighted centroid.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def cell_zone_range(case_file: h5py.File) -> tuple[int, int, int, str]:
    topology = case_file["meshes/1/cells/zoneTopology"]
    ids = topology["id"][:]
    if len(ids) != 1:
        raise ValueError("Only a single Fluent cell zone is currently supported")
    name = topology["name"][0].decode("utf-8", errors="replace")
    return (
        int(ids[0]),
        int(topology["minId"][0]),
        int(topology["maxId"][0]),
        name,
    )


def load_profile(path: Path) -> np.ndarray:
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        reader = csv.DictReader(line for line in stream if not line.startswith("#"))
        for row in reader:
            rows.append([float(row["x_mm"]), float(row["y_mm"])])
    return np.asarray(rows, dtype=float)


def inspect(case_path: Path, data_path: Path, threshold_K: float, top: int) -> dict:
    with h5py.File(data_path, "r") as data_file:
        temperature = data_file["results/1/phase-1/cells/SV_T/1"][:]

    selected = np.flatnonzero(temperature >= threshold_K)
    if top > 0:
        top_indices = np.argpartition(temperature, -min(top, len(temperature)))[-top:]
        selected = np.unique(np.concatenate([selected, top_indices]))
    selected = selected[np.argsort(temperature[selected])[::-1]]

    with h5py.File(case_path, "r") as case_file:
        zone_id, min_id, max_id, zone_name = cell_zone_range(case_file)
        if len(temperature) != max_id - min_id + 1:
            raise ValueError("Temperature array length does not match cell-zone ID range")

        c0 = case_file["meshes/1/faces/c0/1"][:]
        c1 = case_file["meshes/1/faces/c1/1"][:]
        face_node_count = case_file["meshes/1/faces/nodes/1/nnodes"][:]
        face_nodes = case_file["meshes/1/faces/nodes/1/nodes"][:]
        node_coords = case_file["meshes/1/nodes/coords/317"]
        offsets = np.empty(len(face_node_count) + 1, dtype=np.int64)
        offsets[0] = 0
        np.cumsum(face_node_count, out=offsets[1:])

        selected_cell_ids = min_id + selected.astype(np.int64)
        incident_faces: dict[int, list[int]] = {
            int(cell_id): [] for cell_id in selected_cell_ids
        }
        for connectivity in (c0, c1):
            matching_faces = np.flatnonzero(np.isin(connectivity, selected_cell_ids))
            for face_id in matching_faces:
                incident_faces[int(connectivity[face_id])].append(int(face_id))

        rows = []
        for array_index in selected:
            cell_id = min_id + int(array_index)
            face_ids = np.unique(incident_faces[cell_id])
            node_ids: list[int] = []
            for face_id in face_ids:
                node_ids.extend(
                    face_nodes[offsets[face_id] : offsets[face_id + 1]].tolist()
                )
            unique_node_ids = np.unique(node_ids)
            if not len(unique_node_ids):
                raise ValueError(f"No face connectivity found for cell {cell_id}")
            points = node_coords[unique_node_ids - 1, :]
            center = np.mean(points, axis=0)
            lower = np.min(points, axis=0)
            upper = np.max(points, axis=0)
            rows.append(
                {
                    "array_index": int(array_index),
                    "cell_id": cell_id,
                    "cell_zone_id": zone_id,
                    "cell_zone_name": zone_name,
                    "temperature_K": float(temperature[array_index]),
                    "face_count": int(len(face_ids)),
                    "node_count": int(len(unique_node_ids)),
                    "x_vertex_mean_m": float(center[0]),
                    "y_vertex_mean_m": float(center[1]),
                    "z_vertex_mean_m": float(center[2]),
                    "x_min_m": float(lower[0]),
                    "y_min_m": float(lower[1]),
                    "z_min_m": float(lower[2]),
                    "x_max_m": float(upper[0]),
                    "y_max_m": float(upper[1]),
                    "z_max_m": float(upper[2]),
                    "x_extent_mm": float(1000.0 * (upper[0] - lower[0])),
                    "y_extent_mm": float(1000.0 * (upper[1] - lower[1])),
                    "z_extent_mm": float(1000.0 * (upper[2] - lower[2])),
                }
            )

    return {
        "case": str(case_path),
        "data": str(data_path),
        "temperature_dataset": "results/1/phase-1/cells/SV_T/1",
        "threshold_K": threshold_K,
        "temperature_statistics_K": {
            "min": float(np.min(temperature)),
            "mean": float(np.mean(temperature)),
            "max": float(np.max(temperature)),
            "count_at_or_above_threshold": int(np.sum(temperature >= threshold_K)),
            "count_at_or_above_4999_K": int(np.sum(temperature >= 4999.0)),
        },
        "centroid_note": "Locations are vertex means reconstructed from HDF5 connectivity.",
        "cells": rows,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_cells(path: Path, result: dict, profile_path: Path) -> None:
    rows = result["cells"]
    profile = load_profile(profile_path)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    ax = axes[0]
    ax.plot(profile[:, 0], profile[:, 1], "k-", lw=1.2, label="C3X profile")
    for row in rows:
        x = 1000.0 * row["x_vertex_mean_m"]
        y = 1000.0 * row["y_vertex_mean_m"]
        ax.scatter(x, y, c=row["temperature_K"], vmin=2300, vmax=5000, cmap="inferno", s=35)
        if row["temperature_K"] >= 4999.0:
            ax.annotate(str(row["cell_id"]), (x, y), xytext=(4, 4), textcoords="offset points", fontsize=7)
    ax.set(xlabel="x [mm]", ylabel="y [mm]", title="Hot-cell diagnostic locations")
    ax.axis("equal")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)

    ax = axes[1]
    limited = [row for row in rows if row["temperature_K"] >= 4999.0]
    for i, row in enumerate(limited):
        ax.plot([row["z_min_m"] * 1000, row["z_max_m"] * 1000], [i, i], "o-", lw=3)
    ax.set_yticks(range(len(limited)), [str(row["cell_id"]) for row in limited])
    ax.set(xlabel="cell vertex z-range [mm]", ylabel="cell ID", title="5000 K-limited cell span")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--threshold-K", type=float, default=4999.0)
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--profile", default=str(ROOT / "configs" / "c3x_coordinates.csv"))
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    result = inspect(
        Path(args.case).resolve(), Path(args.data).resolve(), args.threshold_K, args.top
    )
    json_path = out_dir / "hot_cell_diagnostics.json"
    csv_path = out_dir / "hot_cell_diagnostics.csv"
    plot_path = out_dir / "hot_cell_locations.png"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_csv(csv_path, result["cells"])
    plot_cells(plot_path, result, Path(args.profile).resolve())
    print(json.dumps(result["temperature_statistics_K"], indent=2))
    print(json_path)
    print(csv_path)
    print(plot_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
