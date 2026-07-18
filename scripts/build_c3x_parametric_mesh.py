"""Generate and inventory a Fluent mesh for a parametric C3X SAT model."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

import bofm.cfd.fluent as F
from bofm.cfd.mesh import DomainBounds, build_watertight_mesh


ROOT = Path(__file__).resolve().parents[1]


def prism_total_thickness(first_height_mm: float, layers: int, growth: float) -> float:
    if abs(growth - 1.0) < 1.0e-12:
        return first_height_mm * layers
    return first_height_mm * (growth ** layers - 1.0) / (growth - 1.0)


def coolant_targets(path: Path) -> dict[str, tuple]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: (*[float(x) for x in spec["center_mm"]], float(spec["mesh_tolerance_mm"]))
        for name, spec in data["boundaries"].items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=("smoke", "coarse", "paper", "fine"), default="smoke")
    parser.add_argument("--sat", default=str(ROOT / "runs" / "parametric" / "baseline" / "c3x_baseline.sat"))
    parser.add_argument("--out-prefix")
    parser.add_argument("--tiers", default=str(ROOT / "configs" / "c3x_mesh_tiers.yaml"))
    parser.add_argument("--targets", default=str(ROOT / "configs" / "c3x_boundary_targets.json"))
    parser.add_argument("--cores", type=int, default=4)
    args = parser.parse_args()

    tiers_path = Path(args.tiers).resolve()
    cfg = yaml.safe_load(tiers_path.read_text(encoding="utf-8"))
    tier = cfg["tiers"][args.tier]
    geom = cfg["geometry"]
    diameter = float(geom["diameter_mm"])
    span = float(geom["span_mm"])
    passage = (ROOT / geom["passage_json"]).resolve()
    prefix = Path(args.out_prefix).resolve() if args.out_prefix else (
        ROOT / "runs" / "parametric" / "baseline" / f"c3x_baseline_{args.tier}"
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    out_mesh = prefix.with_suffix(".msh.h5")
    out_case = prefix.with_suffix(".cas.h5")
    out_meta = prefix.with_name(prefix.name + "_mesh.json")
    out_log = prefix.with_name(prefix.name + "_mesh.log")
    log_handle = out_log.open("w", encoding="utf-8")

    def log(*items):
        text = " ".join(str(x) for x in items)
        print(text, flush=True)
        log_handle.write(text + "\n")
        log_handle.flush()

    first_height = float(tier["first_layer_mm"])
    layers = int(tier["prism_layers"])
    growth = float(tier["prism_growth"])
    metadata = {
        "status": "running",
        "tier": args.tier,
        "purpose": tier["purpose"],
        "source_sat": str(Path(args.sat).resolve()),
        "passage_json": str(passage),
        "periodic_span_mm": span,
        "hole_diameter_mm": diameter,
        "requested": tier,
        "derived": {
            "nominal_cells_across_hole": diameter / float(tier["surface"]["MinSize"]),
            "prism_total_thickness_mm": prism_total_thickness(first_height, layers, growth),
        },
        "host": {"platform": platform.platform(), "logical_processors": os.cpu_count(), "fluent_cores": args.cores},
    }
    session = None
    started = time.perf_counter()
    try:
        bounds = DomainBounds.from_passage_json(passage, span_mm=span)
        targets = coolant_targets(Path(args.targets).resolve())
        session = F.launch(mode="meshing", processor_count=args.cores, ui_mode="no_gui")
        log("Fluent:", session.get_fluent_version())
        log("tier:", args.tier, "surface:", tier["surface"])
        log("prism: first_mm=", first_height, "layers=", layers,
            "growth=", growth, "total_mm=", metadata["derived"]["prism_total_thickness_mm"])
        groups = build_watertight_mesh(
            session,
            Path(args.sat).resolve(),
            bounds,
            out_msh=out_mesh.resolve(),
            n_prism=layers,
            volume_fill=tier["volume_fill"],
            surface_controls=tier["surface"],
            prism_growth_rate=growth,
            first_height_mm=first_height,
            bl_zone_names=["vane_wall", "film_hole_wall"],
            extra_face_targets=targets,
            hole_diameter_mm=diameter,
        )
        cells = int(session.meshing_utilities.get_cell_zone_count(cell_zone_name_pattern="*"))
        faces = int(session.meshing_utilities.get_face_zone_count(face_zone_name_pattern="*"))
        metadata["actual"] = {
            "cell_count": cells,
            "cell_count_M": cells / 1.0e6,
            "face_count": faces,
            "boundary_group_zone_counts": {name: len(ids) for name, ids in groups.items()},
        }
        log("actual cells:", cells, "faces:", faces)
        log("groups:", metadata["actual"]["boundary_group_zone_counts"])
        session.tui.switch_to_solution_mode("yes")
        session.tui.file.write_case(str(out_case.resolve()))
        metadata["status"] = "ok"
        metadata["elapsed_seconds"] = time.perf_counter() - started
        metadata["outputs"] = {"mesh": str(out_mesh), "case": str(out_case), "log": str(out_log)}
        out_meta.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        log("wrote:", out_mesh)
        log("wrote:", out_case)
        log("wrote:", out_meta)
        return 0
    except Exception:
        metadata["status"] = "failed"
        metadata["elapsed_seconds"] = time.perf_counter() - started
        metadata["error"] = traceback.format_exc()
        out_meta.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        log(metadata["error"])
        return 1
    finally:
        try:
            if session is not None:
                session.exit()
        except Exception:
            pass
        log_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
