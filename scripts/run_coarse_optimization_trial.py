"""Run one end-to-end coarse CFD trial from an optimizer design JSON."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_stage(name: str, command: list[str], run_dir: Path, dry_run: bool) -> None:
    log_path = run_dir / f"{name}.log"
    printable = subprocess.list2cmdline(command)
    print(f"[{name}] {printable}", flush=True)
    if dry_run:
        log_path.write_text("DRY_RUN\n" + printable + "\n", encoding="utf-8")
        return
    with log_path.open("w", encoding="utf-8") as stream:
        stream.write(printable + "\n\n")
        stream.flush()
        process = subprocess.run(
            command,
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if process.returncode:
        raise RuntimeError(f"{name} failed with exit code {process.returncode}; see {log_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-json", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--mesh-cores", type=int, default=8)
    parser.add_argument("--solve-cores", type=int, default=8)
    parser.add_argument("--iters", type=int, default=500)
    parser.add_argument("--startup-iters", type=int, default=150)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    design = json.loads(Path(args.design_json).resolve().read_text(encoding="utf-8"))
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    prefix = run_dir / "c3x"
    mesh_prefix = run_dir / "c3x_coarse"
    mesh = mesh_prefix.with_suffix(".msh.h5")
    setup_case = run_dir / "c3x_coarse_setup.cas.h5"
    solution_prefix = run_dir / f"c3x_coarse_iter{args.iters}"
    solution_case = solution_prefix.with_suffix(".cas.h5")
    solution_data = solution_prefix.with_suffix(".dat.h5")
    post_dir = run_dir / f"post_iter{args.iters}"
    iterate_log = run_dir / "solve.log"

    geometry = [
        python, "scripts/build_c3x_workbench_case.py",
        "--template", str(ROOT / "runs/workbench/periodic_v2/template/c3x_kumar_fixed_le_template.scdoc"),
        "--targets", str(ROOT / "runs/workbench/periodic_v2/geometry_freeze/c3x_boundary_targets.json"),
        "--out-prefix", str(prefix),
        "--ss1-s", str(design["SS1_s"]),
        "--ss2-s", str(design["SS2_s"]),
        "--ps1-s", str(design["PS1_s"]),
        "--ps2-s", str(design["PS2_s"]),
        "--suction-angle", str(design["suction_angle_deg"]),
        "--pressure-angle", str(design["pressure_angle_deg"]),
        "--diameter-mm", "0.99",
        "--span-count", "5",
    ]
    run_stage("geometry", geometry, run_dir, args.dry_run)
    run_stage("mesh", [
        python, "scripts/run_fluent_native_cad_mesh.py",
        "--cad", str(prefix.with_suffix(".scdoc")),
        "--tier", "coarse",
        "--tiers", str(ROOT / "runs/kumar_periodic_v2/c3x_mesh_tiers_qualified.yaml"),
        "--cores", str(args.mesh_cores),
        "--out-prefix", str(mesh_prefix),
    ], run_dir, args.dry_run)
    run_stage("setup", [
        python, "scripts/run_workbench_film_setup.py",
        "--case-in", str(mesh),
        "--case-out", str(setup_case),
        "--simulation-case", "kumar_case1_tr3",
        "--cores", str(args.solve_cores),
        "--precision", "single",
    ], run_dir, args.dry_run)
    run_stage("solve", [
        python, "scripts/run_workbench_film_iterate.py",
        "--case", str(setup_case),
        "--iters", str(args.iters),
        "--startup-iters", str(args.startup_iters),
        "--initialization", "hybrid",
        "--out-prefix", str(solution_prefix),
        "--cores", str(args.solve_cores),
        "--precision", "single",
    ], run_dir, args.dry_run)
    run_stage("post", [
        python, "scripts/export_workbench_film_results.py",
        "--case", str(solution_case),
        "--data", str(solution_data),
        "--out-dir", str(post_dir),
        "--log", str(iterate_log),
        "--simulation-case", "kumar_case1_tr3",
        "--cores", "2",
        "--precision", "single",
        "--hole-diameter-mm", "0.99",
    ], run_dir, args.dry_run)
    run_stage("contract", [
        python, "scripts/write_optimization_result.py",
        "--post-dir", str(post_dir),
        "--baseline", str(ROOT / "configs/c3x_optimization_coarse_baseline.json"),
        "--out", str(Path(args.result_json).resolve()),
    ], run_dir, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
