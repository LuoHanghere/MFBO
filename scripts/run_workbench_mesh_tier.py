"""Generate a Workbench Route B mesh tier through RunWB2 + Fluent Meshing.

This script automates the formerly manual Workbench meshing step as far as the
current workstation allows. It writes a `.msh.h5`; the solver setup step can read
that mesh and write a `.cas.h5`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUNWB2 = Path(r"D:\Ansys\ANSYS Inc\v242\Framework\bin\Win64\runwb2.bat")


def file_record(path: Path) -> dict[str, Any]:
    p = path.resolve()
    if not p.exists():
        return {"path": str(p), "exists": False}
    st = p.stat()
    return {
        "path": str(p),
        "exists": True,
        "bytes": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }


def wb_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\")


def wb_py_command(code: str) -> str:
    """Return a Workbench-journal Python literal for a Fluent `%py-exec` command."""
    command = '(%py-exec "' + code.replace('"', r'\"') + '")'
    return repr(command)


def write_journal(
    path: Path,
    *,
    dsco: Path,
    out_mesh: Path,
    tier: dict[str, Any],
    volume_max_m: float,
    skip_boundary_layers: bool,
) -> None:
    layers = int(tier["prism_layers"])
    first_height_m = float(tier["first_layer_mm"]) * 1.0e-3
    prism_growth = float(tier["prism_growth"])
    if skip_boundary_layers:
        bl_block = '    status["steps"].append("skipped boundary layers")\n'
    else:
        bl_state = {
            r"AddChild": r"yes",
            r"BLControlName": r"smooth-transition_1",
            r"OffsetMethodType": r"smooth-transition",
            r"NumberOfLayers": layers,
            r"FirstHeight": first_height_m,
            r"Rate": prism_growth,
            r"FaceScope": {
                r"FaceScopeMeshObject": r"",
                r"GrowOn": r"only-walls",
                r"RegionsType": r"fluid-regions",
                r"TopologyList": [],
            },
            r"LocalPrismPreferences": {
                r"Continuous": r"Continuous",
                r"IgnoreBoundaryLayers": r"no",
                r"SplitPrism": r"No",
                r"InvalidNormalMethod": r"Create Spheres",
                r"ModifyAtInvalidNormals": r"no",
                r"RemeshAtInvalidNormals": r"no",
                r"NumberOfSplitLayers": 3,
                r"SmoothRingsAtInvalidNormals": 3,
                r"SphereRadiusFactorAtInvalidNormals": 0.8,
                r"AllowedTangencyAtInvalidNormals": 0.98,
            },
        }
        child_state = dict(bl_state)
        child_state.update(
            {
                r"BLRegionList": [r"fixed_fluid_domain"],
                r"BLZoneList": [
                    r"fixed_fluid_domain:1",
                    r"periodic_low",
                    r"periodic_high",
                    r"span_low",
                    r"span_high",
                    r"vane_wall",
                ],
            }
        )
        set_bl_args = (
            "workflow.TaskObject['Add Boundary Layers'].Arguments.set_state("
            + repr(bl_state)
            + ")"
        )
        set_existing_child = (
            "workflow.TaskObject['smooth-transition_1'].Arguments.set_state("
            + repr(child_state)
            + ")"
        )
        execute_existing_child = "workflow.TaskObject['smooth-transition_1'].Execute()"
        add_bl = "workflow.TaskObject['Add Boundary Layers'].AddChildAndUpdate(DeferUpdate=False)"
        exec_bl = "workflow.TaskObject['Add Boundary Layers'].Execute()"
        bl_block = f'''    status["boundary_layers_attempts"] = []
    try:
        setup1.SendCommand(Command={wb_py_command(set_bl_args)})
        status["steps"].append("set boundary layer arguments")
        status["boundary_layers_attempts"].append({{"method": "Arguments.set_state", "ok": True}})
    except Exception as e:
        status["boundary_layers_attempts"].append({{"method": "Arguments.set_state", "ok": False, "error": repr(e)}})
        raise
    for method, cmd_literal in (
        ("AddChildAndUpdate", {wb_py_command(add_bl)}),
        ("UpdateExistingChildArguments", {wb_py_command(set_existing_child)}),
        ("ExecuteExistingChild", {wb_py_command(execute_existing_child)}),
        ("ExecuteParent", {wb_py_command(exec_bl)}),
    ):
        try:
            setup1.SendCommand(Command=cmd_literal)
            status["steps"].append("boundary layers via " + method)
            status["boundary_layers_attempts"].append({{"method": method, "ok": True}})
            if method in ("AddChildAndUpdate", "ExecuteExistingChild", "ExecuteParent"):
                break
        except Exception as e:
            status["boundary_layers_attempts"].append({{"method": method, "ok": False, "error": repr(e)}})
    else:
        raise RuntimeError("boundary layer insertion failed via both Execute and AddChildAndUpdate")
'''
    journal = f"""# encoding: utf-8
import json
import os
import shutil

status = {{"steps": []}}
try:
    system2 = GetSystem(Name="FLTG")
    setup1 = system2.GetContainer(ComponentName="Setup")
    mesh1 = system2.GetContainer(ComponentName="Mesh")
    Fluent.Edit(Container=mesh1)
    status["steps"].append("opened Fluent mesh container")

    setup1.SendCommand(Command="(%py-exec \\"meshing.GlobalSettings.LengthUnit.set_state(r'm')\\")")
    setup1.SendCommand(Command="(%py-exec \\"meshing.GlobalSettings.AreaUnit.set_state(r'm^2')\\")")
    setup1.SendCommand(Command="(%py-exec \\"meshing.GlobalSettings.VolumeUnit.set_state(r'm^3')\\")")

    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Import Geometry'].Arguments.set_state({{r'FileName': r'{wb_path(dsco)}', r'ImportCadPreferences': {{r'MaxFacetLength': 0,}}, r'LengthUnit': r'm', r'UseBodyLabels': r'Yes',}})\\")")
    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Import Geometry'].Execute()\\")")
    status["steps"].append("imported geometry")

    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Generate the Surface Mesh'].Execute()\\")")
    status["steps"].append("generated surface mesh")

    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Describe Geometry'].Arguments.set_state({{r'NonConformal': r'No', r'SetupType': r'The geometry consists of only fluid regions with no voids',}})\\")")
    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Describe Geometry'].UpdateChildTasks(SetupTypeChanged=True)\\")")
    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Describe Geometry'].Execute()\\")")
    status["steps"].append("described geometry")

    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Update Boundaries'].Arguments.set_state({{r'BoundaryLabelList': [r'inlet', r'qian', r'ss', r'ps'], r'BoundaryLabelTypeList': [r'pressure-inlet', r'velocity-inlet', r'pressure-inlet', r'pressure-inlet'], r'OldBoundaryLabelList': [r'inlet', r'qian', r'ss', r'ps'], r'OldBoundaryLabelTypeList': [r'velocity-inlet', r'wall', r'wall', r'wall'],}})\\")")
    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Update Boundaries'].Execute()\\")")
    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Update Regions'].Execute()\\")")
    status["steps"].append("updated boundaries/regions")

{bl_block}

    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Generate the Volume Mesh'].Arguments.set_state({{r'VolumeFill': r'polyhedra', r'VolumeFillControls': {{r'MaxSize': {volume_max_m:.12g},}},}})\\")")
    setup1.SendCommand(Command="(%py-exec \\"workflow.TaskObject['Generate the Volume Mesh'].Execute()\\")")
    status["steps"].append("generated volume mesh")

    dst = r"{wb_path(out_mesh)}"
    dstdir = os.path.dirname(dst)
    if not os.path.isdir(dstdir):
        os.makedirs(dstdir)
    if os.path.exists(dst):
        os.remove(dst)
    setup1.SendCommand(Command="(%py-exec \\"\\nimport json, os\\ndst = r'{wb_path(out_mesh)}'\\nattempts = []\\ntry:\\n    meshing.File.WriteMesh(FileName=dst)\\n    attempts.append({{'expr': 'meshing.File.WriteMesh(FileName=dst)', 'ok': True, 'exists': os.path.exists(dst)}})\\nexcept Exception as e:\\n    attempts.append({{'expr': 'meshing.File.WriteMesh(FileName=dst)', 'ok': False, 'error': repr(e), 'exists': os.path.exists(dst)}})\\nwith open(r'{wb_path(path.with_suffix('.write_status.json'))}', 'w') as f:\\n    f.write(json.dumps({{'dst': dst, 'attempts': attempts, 'exists': os.path.exists(dst)}}, indent=2))\\n\\")")
    status["steps"].append("wrote mesh")
    status["output_mesh"] = {{"dst": dst, "exists": os.path.exists(dst)}}
except Exception as e:
    status["error"] = repr(e)

with open(r"{wb_path(path.with_suffix('.status.json'))}", "w") as f:
    f.write(json.dumps(status, indent=2))
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(journal, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["smoke", "coarse", "paper", "fine"], required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--project", default=str(ROOT / "1.wbpj"))
    ap.add_argument("--dsco", default=str(ROOT / "1_files" / "dp0" / "Disco" / "DM" / "Disco.dsco"))
    ap.add_argument("--mesh-tiers-yaml", default=str(ROOT / "configs" / "c3x_mesh_tiers.yaml"))
    ap.add_argument("--out-mesh", default=None)
    ap.add_argument("--out-meta", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prism-layers", type=int, default=None,
                    help="Override tier prism layers for debugging/conservative smoke tests")
    ap.add_argument("--skip-boundary-layers", action="store_true",
                    help="Debug only: generate volume mesh without adding prism layers")
    args = ap.parse_args()

    name = args.name or f"baseline_{args.tier}"
    out_dir = ROOT / "runs" / "workbench" / "grid_independence" / args.tier
    out_mesh = Path(args.out_mesh).resolve() if args.out_mesh else (out_dir / f"{name}_mesh.msh.h5").resolve()
    out_meta = Path(args.out_meta).resolve() if args.out_meta else (out_dir / f"{name}_mesh_meta.json").resolve()
    journal = out_dir / "logs" / f"{name}_workbench_mesh.wbjn"
    log = out_dir / "logs" / f"{name}_workbench_mesh.log"

    tiers_doc = yaml.safe_load(Path(args.mesh_tiers_yaml).read_text(encoding="utf-8"))
    tier = tiers_doc["tiers"][args.tier]
    if args.prism_layers is not None:
        tier = dict(tier)
        tier["prism_layers"] = int(args.prism_layers)
    volume_max_m = float(tier["surface"]["MaxSize"]) * 1.0e-3
    write_journal(
        journal,
        dsco=Path(args.dsco).resolve(),
        out_mesh=out_mesh,
        tier=tier,
        volume_max_m=volume_max_m,
        skip_boundary_layers=args.skip_boundary_layers,
    )

    meta = {
        "name": name,
        "tier": args.tier,
        "route": "workbench_batch_fluent_meshing",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project": file_record(Path(args.project)),
        "dsco": file_record(Path(args.dsco)),
        "journal": file_record(journal),
        "tier_config": tier,
        "automated_controls": {
            "volume_max_m": volume_max_m,
            "prism_layers": int(tier["prism_layers"]),
            "skip_boundary_layers": bool(args.skip_boundary_layers),
            "note": "Workbench batch controls volume MaxSize and prism layer count; first-layer height and detailed scoped surface sizing still need verification against Fluent Meshing task support.",
        },
        "output_mesh": file_record(out_mesh),
    }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    cmd = [str(RUNWB2), "-B", "-F", str(Path(args.project).resolve()), "-R", str(journal.resolve())]
    if args.dry_run:
        print("DRY_RUN:", " ".join(cmd))
        print("journal:", journal)
        print("mesh:", out_mesh)
        return 0

    print("RUN:", " ".join(cmd))
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as f:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, text=True)
    status_path = journal.with_suffix(".status.json")
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    meta["workbench_log"] = file_record(log)
    meta["workbench_status"] = status
    meta["output_mesh"] = file_record(out_mesh)
    out_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(f"RunWB2 failed with {proc.returncode}; see {log}")
    if not out_mesh.exists():
        raise SystemExit(f"Workbench did not create expected mesh: {out_mesh}; see {status_path}")
    print("wrote:", out_mesh)
    print("meta:", out_meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
