"""Run the standard Route B Workbench validation pipeline for one mesh tier.

The only non-automated prerequisite is the Workbench/Fluent Meshing export:
``--case-in`` must point to the `.cas.h5` mesh case written from Workbench with
named zones preserved.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


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


def default_periodic_width_mm() -> float:
    path = ROOT / "configs" / "c3x_kumar_paper_external_flow.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return float(data.get("periodic_width_mm", data.get("pitch_mm", 117.73)))
    except Exception:
        return 117.73


def run_logged(cmd: list[str], log_path: Path, *, dry_run: bool = False) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header = " ".join(cmd)
    if dry_run:
        log_path.write_text("DRY_RUN\n" + header + "\n", encoding="utf-8")
        print("DRY_RUN:", header)
        return
    print("RUN:", header)
    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(header + "\n\n")
        logf.flush()
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            stdout=logf,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if proc.returncode != 0:
        raise SystemExit(f"step failed ({proc.returncode}), see {log_path}")


def write_mesh_meta(
    out: Path,
    *,
    name: str,
    tier: str,
    case_in: Path,
    mesh_tiers_yaml: Path,
    layout: Path,
) -> None:
    doc = yaml.safe_load(mesh_tiers_yaml.read_text(encoding="utf-8"))
    tier_doc = doc["tiers"][tier]
    payload = {
        "name": name,
        "route": "workbench",
        "tier": tier,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "case_in": file_record(case_in),
        "layout": file_record(layout),
        "tier_config": tier_doc,
        "actual": {
            "cell_count": None,
            "face_count": None,
            "node_count": None,
            "note": "Fill after Workbench/Fluent mesh count is recorded; setup/export still records case/data file sizes.",
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="Run name, e.g. baseline_coarse")
    ap.add_argument("--tier", choices=["smoke", "coarse", "paper", "fine"], required=True)
    ap.add_argument("--case-in", required=True, help="Workbench/Fluent Meshing exported .cas.h5 or .msh.h5")
    ap.add_argument("--design", default=str(ROOT / "runs" / "workbench" / "baseline" / "c3x_wb_baseline_design.json"))
    ap.add_argument("--layout", default=str(ROOT / "runs" / "workbench" / "baseline" / "c3x_wb_baseline_layout.json"))
    ap.add_argument("--mesh-tiers-yaml", default=str(ROOT / "configs" / "c3x_mesh_tiers.yaml"))
    ap.add_argument("--simulation-case", default="nasa_44344_validation")
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--startup-iters", type=int, default=200)
    ap.add_argument("--flow-only-startup-iters", type=int, default=0)
    ap.add_argument("--initial-state-json")
    ap.add_argument("--initial-velocity-scale", type=float, default=1.0)
    ap.add_argument("--initial-pressure-pa", type=float)
    ap.add_argument("--initial-temperature-k", type=float)
    ap.add_argument("--initial-k", type=float)
    ap.add_argument("--initial-epsilon", type=float)
    ap.add_argument("--initialization", choices=["hybrid", "standard"], default="hybrid")
    ap.add_argument("--cores", type=int, default=16)
    ap.add_argument("--precision", choices=["single", "double"], default="single")
    ap.add_argument("--span-mm", type=float, default=14.85)
    ap.add_argument("--pitch-mm", type=float)
    ap.add_argument("--out-root", default=str(ROOT / "runs" / "workbench" / "grid_independence"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-setup", action="store_true")
    ap.add_argument("--skip-iterate", action="store_true")
    ap.add_argument("--skip-export", action="store_true")
    args = ap.parse_args()

    case_in = Path(args.case_in).resolve()
    design = Path(args.design).resolve()
    layout = Path(args.layout).resolve()
    mesh_tiers_yaml = Path(args.mesh_tiers_yaml).resolve()
    out_root = Path(args.out_root).resolve()
    pitch_mm = args.pitch_mm if args.pitch_mm is not None else default_periodic_width_mm()
    run_dir = out_root / args.tier
    logs = run_dir / "logs"
    run_dir.mkdir(parents=True, exist_ok=True)

    topology_json = run_dir / f"{args.name}_topology_check.json"
    mesh_meta = run_dir / f"{args.name}_mesh_meta.json"
    setup_case = run_dir / f"{args.name}_setup.cas.h5"
    run_prefix = run_dir / f"{args.name}_iter{args.iters}"
    run_case = run_prefix.with_suffix(".cas.h5")
    run_data = run_prefix.with_suffix(".dat.h5")
    post_dir = run_dir / f"post_iter{args.iters}"
    manifest = run_dir / f"{args.name}_iter{args.iters}_manifest.json"
    iterate_log = logs / f"{args.name}_iterate{args.iters}.log"

    write_mesh_meta(
        mesh_meta,
        name=args.name,
        tier=args.tier,
        case_in=case_in,
        mesh_tiers_yaml=mesh_tiers_yaml,
        layout=layout,
    )

    run_logged([
        sys.executable,
        "scripts/validate_workbench_layout.py",
        "--layout", str(layout),
        "--out-json", str(topology_json),
    ], logs / f"{args.name}_topology.log", dry_run=args.dry_run)

    if not args.skip_setup:
        run_logged([
            sys.executable,
            "scripts/run_workbench_film_setup.py",
            "--case-in", str(case_in),
            "--case-out", str(setup_case),
            "--span-mm", str(args.span_mm),
            "--pitch-mm", str(pitch_mm),
            "--simulation-case", args.simulation_case,
            "--cores", str(args.cores),
            "--precision", args.precision,
        ], logs / f"{args.name}_setup.log", dry_run=args.dry_run)

    if not args.skip_iterate:
        iterate_cmd = [
            sys.executable,
            "scripts/run_workbench_film_iterate.py",
            "--case", str(setup_case),
            "--iters", str(args.iters),
            "--startup-iters", str(args.startup_iters),
            "--flow-only-startup-iters", str(args.flow_only_startup_iters),
            "--initialization", args.initialization,
            "--out-prefix", str(run_prefix),
            "--cores", str(args.cores),
            "--precision", args.precision,
        ]
        if args.initial_state_json:
            iterate_cmd.extend([
                "--initial-state-json", str(Path(args.initial_state_json).resolve())
            ])
        iterate_cmd.extend([
            "--initial-velocity-scale", str(args.initial_velocity_scale)
        ])
        for option, value in (
            ("--initial-pressure-pa", args.initial_pressure_pa),
            ("--initial-temperature-k", args.initial_temperature_k),
            ("--initial-k", args.initial_k),
            ("--initial-epsilon", args.initial_epsilon),
        ):
            if value is not None:
                iterate_cmd.extend([option, str(value)])
        run_logged(iterate_cmd, iterate_log, dry_run=args.dry_run)

    if not args.skip_export:
        run_logged([
            sys.executable,
            "scripts/export_workbench_film_results.py",
            "--case", str(run_case),
            "--data", str(run_data),
            "--out-dir", str(post_dir),
            "--log", str(iterate_log),
            "--simulation-case", args.simulation_case,
            "--cores", "4",
            "--precision", args.precision,
        ], logs / f"{args.name}_export.log", dry_run=args.dry_run)
        if args.simulation_case.startswith("kumar_case1"):
            run_logged([
                sys.executable,
                "scripts/compare_kumar_eta.py",
                "--post-dir", str(post_dir),
            ], logs / f"{args.name}_kumar_compare.log", dry_run=args.dry_run)

    run_logged([
        sys.executable,
        "scripts/write_workbench_run_manifest.py",
        "--name", args.name,
        "--mesh-tier", args.tier,
        "--simulation-case", args.simulation_case,
        "--design", str(design),
        "--layout", str(layout),
        "--topology", str(topology_json),
        "--mesh-case", str(case_in),
        "--mesh-meta", str(mesh_meta),
        "--setup-case", str(setup_case),
        "--run-case", str(run_case),
        "--run-data", str(run_data),
        "--post-dir", str(post_dir),
        "--log", str(iterate_log),
        "--out", str(manifest),
    ], logs / f"{args.name}_manifest.log", dry_run=args.dry_run)

    print("manifest:", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
