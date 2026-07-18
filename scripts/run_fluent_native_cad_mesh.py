"""Generate a Fluent mesh directly from native SpaceClaim/Discovery CAD.

This is Route A: native CAD -> headless Fluent Meshing, with no Workbench
project/container and no SAT conversion.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

import bofm.cfd.fluent as F


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LABELS = [
    "inlet",
    "outlet",
    "periodic_low",
    "periodic_high",
    "span_low",
    "span_high",
    "vane_wall",
    "film_hole_wall",
    "qian",
    "ss",
    "ps",
]


def _run(task, state: dict | None = None) -> None:
    if state:
        task.Arguments.set_state(state)
    task.Execute()


def _zone_names(session) -> list[str]:
    mu = session.meshing_utilities
    ids = list(mu.get_face_zones(filter="*"))
    return [str(x) for x in mu.convert_zone_ids_to_name_strings(zone_id_list=ids)]


def normalize_native_cad_boundary_zones(session) -> dict[str, list[str]]:
    """Normalize native-CAD label suffixes on a merged, single-cell-zone mesh."""
    mu = session.meshing_utilities
    ids = list(mu.get_face_zones(filter="*"))
    names = [str(x) for x in mu.convert_zone_ids_to_name_strings(zone_id_list=ids)]
    groups: dict[str, list[tuple[int, str]]] = {
        name: [] for name in EXPECTED_LABELS + ["plenum_wall"]
    }
    for zid, name in zip(ids, names):
        zone_type = str(mu.get_zone_type(zone_id=zid))
        if zone_type in {"interior", "internal"}:
            continue
        target = next(
            (
                base
                for base in EXPECTED_LABELS
                if name == base or name.startswith(base + "-")
            ),
            None,
        )
        if name == "zone-3":
            target = "span_low"
        elif name == "zone-4":
            target = "span_high"
        elif name == "zone-7":
            target = "plenum_wall"
        if target:
            groups[target].append((int(zid), name))

    normalized: dict[str, list[str]] = {}
    for target, members in groups.items():
        if not members:
            continue
        original_names = [name for _, name in members]
        if len(members) == 1:
            zid, name = members[0]
            if name != target:
                mu.rename_face_zone(zone_id=zid, new_name=target)
            normalized[target] = original_names
            continue

        prefix = f"bofm_norm_{target}_"
        member_ids = []
        for index, (zid, _) in enumerate(members):
            mu.rename_face_zone(zone_id=zid, new_name=f"{prefix}{index}")
            member_ids.append(zid)
        mu.merge_face_zones(face_zone_id_list=member_ids)

        current_ids = list(mu.get_face_zones(filter="*"))
        current_names = [
            str(x) for x in mu.convert_zone_ids_to_name_strings(zone_id_list=current_ids)
        ]
        candidates = [
            (int(zid), name)
            for zid, name in zip(current_ids, current_names)
            if name.startswith(prefix)
        ]
        if len(candidates) != 1:
            raise RuntimeError(
                f"could not reduce {target} to one face zone: {candidates}"
            )
        mu.rename_face_zone(zone_id=candidates[0][0], new_name=target)
        normalized[target] = original_names
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cad",
        default=str(ROOT / "runs" / "workbench" / "baseline" / "c3x_wb_baseline.scdoc"),
    )
    parser.add_argument("--tier", choices=("smoke", "coarse", "paper", "fine"), default="smoke")
    parser.add_argument("--tiers", default=str(ROOT / "configs" / "c3x_mesh_tiers.yaml"))
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out-prefix")
    parser.add_argument(
        "--volume-fill",
        choices=("polyhedra",),
        default="polyhedra",
        help="Route-A production is locked to polyhedra",
    )
    args = parser.parse_args()

    cad = Path(args.cad).resolve()
    tiers_path = Path(args.tiers).resolve()
    config = yaml.safe_load(tiers_path.read_text(encoding="utf-8"))
    tier = config["tiers"][args.tier]
    prefix = (
        Path(args.out_prefix).resolve()
        if args.out_prefix
        else ROOT / "runs" / "direct_cad" / args.tier / f"baseline_{args.tier}"
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    mesh_path = prefix.with_suffix(".msh.h5")
    status_path = prefix.with_name(prefix.name + "_mesh_meta.json")
    volume_fill = args.volume_fill
    surface = {
        "MinSize": float(tier["surface"]["MinSize"]) / 1000.0,
        "MaxSize": float(tier["surface"]["MaxSize"]) / 1000.0,
        "GrowthRate": float(tier["surface"]["GrowthRate"]),
    }
    offset_method = str(tier.get("offset_method", "smooth-transition"))
    bl_state = {
        "AddChild": "yes",
        "BLControlName": "smooth-transition_1",
        # Fluent 2024 R2's watertight task accepts smooth-transition/uniform/
        # aspect-ratio/last-ratio here.  FirstHeight is still accepted as the
        # explicit initial-height control with smooth-transition.
        "OffsetMethodType": offset_method,
        "NumberOfLayers": int(tier["prism_layers"]),
        "FirstHeight": float(tier["first_layer_mm"]) / 1000.0,
        "Rate": float(tier["prism_growth"]),
        "FaceScope": "only-walls",
        "BLRegionList": ["fluid-regions"],
        "LocalPrismPreferences": {
            "IgnoreBoundaryLayers": "no",
            "Continuous": "Continuous",
            "ShowLocalPrismPreferences": True,
        },
    }
    result: dict = {
        "status": "running",
        "route": "native_cad_to_fluent_meshing",
        "cad": str(cad),
        "tier": args.tier,
        "cores": args.cores,
        "surface_controls_m": surface,
        "boundary_layer": bl_state,
        "volume_fill": volume_fill,
        "mesh": str(mesh_path),
        "steps": [],
    }
    if mesh_path.exists():
        result["replaced_existing_mesh_bytes"] = mesh_path.stat().st_size
        mesh_path.unlink()
        result["steps"].append("removed stale output mesh before write")
    session = None
    started = time.perf_counter()
    try:
        if not cad.is_file():
            raise FileNotFoundError(cad)
        session = F.launch(mode="meshing", processor_count=args.cores, ui_mode="no_gui")
        result["fluent_version"] = str(session.get_fluent_version())
        workflow = session.workflow
        workflow.InitializeWorkflow(WorkflowType="Watertight Geometry")

        _run(
            workflow.TaskObject["Import Geometry"],
            {
                "FileName": str(cad),
                "LengthUnit": "m",
                "UseBodyLabels": "Yes",
                "CadImportOptions": {
                    "ImportNamedSelections": True,
                    "ImportPartNames": True,
                },
            },
        )
        result["steps"].append("imported native CAD")
        result["zones_after_import"] = _zone_names(session)

        _run(
            workflow.TaskObject["Generate the Surface Mesh"],
            {"CFDSurfaceMeshControls": surface},
        )
        result["steps"].append("generated surface mesh")

        describe = workflow.TaskObject["Describe Geometry"]
        describe.UpdateChildTasks(SetupTypeChanged=False)
        describe.Arguments.set_state(
            {
                "NonConformal": "No",
                "SetupType": "The geometry consists of only fluid regions with no voids",
            }
        )
        describe.UpdateChildTasks(SetupTypeChanged=True)
        describe.Execute()
        result["steps"].append("described fluid-only geometry")

        _run(
            workflow.TaskObject["Update Boundaries"],
            {
                "BoundaryLabelList": ["inlet", "qian", "ss", "ps"],
                "BoundaryLabelTypeList": [
                    "pressure-inlet",
                    "pressure-inlet",
                    "pressure-inlet",
                    "pressure-inlet",
                ],
                "OldBoundaryLabelList": ["inlet", "qian", "ss", "ps"],
                "OldBoundaryLabelTypeList": ["velocity-inlet", "wall", "wall", "wall"],
            },
        )
        _run(workflow.TaskObject["Update Regions"])
        result["steps"].append("updated boundaries and regions")

        bl_parent = workflow.TaskObject["Add Boundary Layers"]
        bl_parent.Arguments.set_state(bl_state)
        bl_parent.AddChildAndUpdate(DeferUpdate=False)
        result["steps"].append("created and generated boundary layers")

        # Keep the native Fluent defaults here.  In particular, allowing the
        # prism/core merge avoids duplicate ``*-quad`` boundary zones and is
        # what the successful GUI-generated reference workflow records.
        _run(
            workflow.TaskObject["Generate the Volume Mesh"],
            {"VolumeFill": volume_fill},
        )
        result["steps"].append("generated volume mesh")
        result["zone_normalization"] = normalize_native_cad_boundary_zones(session)
        result["steps"].append("normalized native-CAD boundary zones")
        # TUI treats backslash escapes such as ``\n`` inside Windows paths as
        # control characters. Forward slashes are accepted by Fluent on Windows.
        session.tui.file.write_mesh(F.tui_path(mesh_path))
        result["steps"].append("wrote mesh")

        names = _zone_names(session)
        try:
            quality_limits = session.meshing_utilities.get_cell_quality_limits(
                cell_zone_name_pattern="*", measure="Orthogonal Quality"
            )
        except Exception as exc:
            quality_limits = {"error": repr(exc)}
        result.update(
            {
                "status": "ok",
                "mesh_exists": mesh_path.is_file(),
                "mesh_bytes": mesh_path.stat().st_size if mesh_path.is_file() else 0,
                "cell_count": int(
                    session.meshing_utilities.get_cell_zone_count(cell_zone_name_pattern="*")
                ),
                "face_count": int(
                    session.meshing_utilities.get_face_zone_count(face_zone_name_pattern="*")
                ),
                "orthogonal_quality_limits": quality_limits,
                "final_zone_names": names,
                "expected_zone_face_counts": {
                    name: int(
                        session.meshing_utilities.get_face_zone_count(
                            face_zone_name_pattern=name
                        )
                    )
                    for name in EXPECTED_LABELS
                },
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
    except Exception:
        result.update(
            {
                "status": "failed",
                "error": traceback.format_exc(),
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
    finally:
        try:
            if session is not None:
                session.exit()
        except Exception:
            pass
        status_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
