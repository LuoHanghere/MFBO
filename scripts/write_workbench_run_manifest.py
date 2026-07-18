"""Write a standardized manifest for one Workbench Route B CFD evaluation."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def file_record(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--mesh-tier", default="unknown")
    ap.add_argument("--simulation-case", default="nasa_44344_validation")
    ap.add_argument("--design")
    ap.add_argument("--layout")
    ap.add_argument("--topology")
    ap.add_argument("--mesh-case")
    ap.add_argument("--mesh-meta")
    ap.add_argument("--setup-case")
    ap.add_argument("--run-case")
    ap.add_argument("--run-data")
    ap.add_argument("--post-dir")
    ap.add_argument("--log")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    design_path = Path(args.design) if args.design else None
    layout_path = Path(args.layout) if args.layout else None
    topology_path = Path(args.topology) if args.topology else None
    mesh_case_path = Path(args.mesh_case) if args.mesh_case else None
    mesh_meta_path = Path(args.mesh_meta) if args.mesh_meta else None
    setup_case = Path(args.setup_case) if args.setup_case else None
    run_case = Path(args.run_case) if args.run_case else None
    run_data = Path(args.run_data) if args.run_data else None
    post_dir = Path(args.post_dir) if args.post_dir else None
    log_path = Path(args.log) if args.log else None

    layout = load_json(layout_path)
    topology = load_json(topology_path)
    mesh_meta = load_json(mesh_meta_path)
    bo_summary = load_json(post_dir / "bo_summary.json") if post_dir else None
    convergence = load_json(post_dir / "convergence_summary.json") if post_dir else None
    nasa_pressure = (
        load_json(post_dir / "nasa_surface_pressure_summary.json") if post_dir else None
    )

    manifest = {
        "name": args.name,
        "route": "workbench",
        "simulation_case": args.simulation_case,
        "mesh_tier": args.mesh_tier,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": {
            "topology_ok": None if topology is None else topology.get("ok"),
            "post_valid": None if bo_summary is None else bo_summary.get("valid"),
        },
        "inputs": {
            "design": file_record(design_path),
            "layout": file_record(layout_path),
            "topology": file_record(topology_path),
            "mesh_case": file_record(mesh_case_path),
            "mesh_meta": file_record(mesh_meta_path),
            "setup_case": file_record(setup_case),
        },
        "outputs": {
            "run_case": file_record(run_case),
            "run_data": file_record(run_data),
            "post_dir": file_record(post_dir),
            "log": file_record(log_path),
        },
        "geometry_summary": {
            "diameter_mm": None if not layout else layout.get("geometry", {}).get("diameter_mm"),
            "periodic_span_mm": None if not layout else layout.get("geometry", {}).get("periodic_span_mm"),
            "row_count": None if not layout else len(layout.get("rows", [])),
        },
        "mesh_summary": None if mesh_meta is None else mesh_meta.get("actual", mesh_meta),
        "topology_summary": None if topology is None else {
            "ok": topology.get("ok"),
            "error_count": topology.get("error_count"),
            "warning_count": topology.get("warning_count"),
            "marker_count": topology.get("marker_count"),
            "cavity_checked_markers": topology.get("cavity_checked_markers"),
            "cavity_failed_markers": topology.get("cavity_failed_markers"),
        },
        "result_summary": None if bo_summary is None else {
            "valid": bo_summary.get("valid"),
            "eta_bar": bo_summary.get("objective", {}).get("eta_bar"),
            "protected_eta_bar": bo_summary.get("objective", {}).get("protected_eta_bar"),
            "coolant_mass_flow_ratio": bo_summary.get("constraints", {}).get("coolant_mass_flow_ratio"),
            "mass_imbalance": bo_summary.get("constraints", {}).get("mass_imbalance"),
            "pressure_loss": bo_summary.get("constraints", {}).get("pressure_loss"),
            "y_plus_p95": bo_summary.get("constraints", {}).get("y_plus_p95"),
            "y_plus_max": bo_summary.get("constraints", {}).get("y_plus_max"),
            "mass_flow_report_available": bo_summary.get("diagnostics", {}).get("mass_flow_report_available"),
            "last_residual_row": bo_summary.get("diagnostics", {}).get("convergence", {}).get("last_residual_row"),
            "warnings": bo_summary.get("diagnostics", {}).get("convergence", {}).get("warnings"),
            "nasa_surface_pressure": nasa_pressure,
        },
        "convergence_summary": convergence,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("wrote:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
