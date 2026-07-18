"""Run one NASA C3X CFD optimization trial at the requested mesh fidelity."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def environment_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser()


BASE_DESIGN = environment_path(
    "BOFM_C3X_BASE_DESIGN",
    ROOT / "runs/nasa_44344/geometry/c3x_nasa44344_periodic_v2_design.json",
)
TEMPLATE = environment_path(
    "BOFM_C3X_TEMPLATE",
    ROOT / "runs/workbench/periodic_v2/template/c3x_kumar_fixed_le_template.scdoc",
)
TARGETS = environment_path(
    "BOFM_C3X_BOUNDARY_TARGETS",
    ROOT / "runs/workbench/periodic_v2/geometry_freeze/c3x_boundary_targets.json",
)
TIERS = ROOT / "configs/c3x_mesh_tiers.yaml"
DEFAULT_ITERS = {"coarse": 1800, "paper": 2500}
DEFAULT_STARTUP_ITERS = {"coarse": 400, "paper": 500}
DEFAULT_REPAIR_PASSES = {"coarse": 0, "paper": 1}
BASELINES = {
    "coarse": ROOT / "configs/c3x_nasa_optimization_baseline_coarse.json",
    "paper": ROOT / "configs/c3x_nasa_optimization_baseline_paper.json",
}

BASELINE_DIAMETER_MM = 0.99
BASELINE_SPAN_COUNT = 5


def resolve_hole_geometry(design: dict) -> tuple[float, int]:
    """Resolve optional 8D hole variables while preserving old 6D designs."""
    diameter_mm = float(design.get("diameter_mm", BASELINE_DIAMETER_MM))
    raw_count = float(design.get("span_count", BASELINE_SPAN_COUNT))
    span_count = int(round(raw_count))
    if diameter_mm <= 0.0:
        raise ValueError("diameter_mm must be positive")
    if span_count < 1 or abs(raw_count - span_count) > 1e-9:
        raise ValueError("span_count must be a positive integer")
    return diameter_mm, span_count


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


RESIDUAL_ROW = re.compile(r"^\s*(\d+)\s+(?:[0-9.]+e[+-]\d+\s+){6,}", re.IGNORECASE)


def run_stage(
    name: str,
    command: list[str],
    run_dir: Path,
    dry_run: bool,
    *,
    echo_solver_progress: bool = False,
) -> None:
    log_path = run_dir / f"{name}.log"
    printable = subprocess.list2cmdline(command)
    try:
        print(f"[{name}] {printable}", flush=True)
    except OSError:
        # A detached Windows parent can close its inherited console pipe while
        # the long-running CFD child remains healthy. Stage logs are canonical.
        pass
    if dry_run:
        log_path.write_text("DRY_RUN\n" + printable + "\n", encoding="utf-8")
        return
    with log_path.open("w", encoding="utf-8") as stream:
        stream.write(printable + "\n\n")
        stream.flush()
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            stream.write(line)
            match = RESIDUAL_ROW.match(line)
            if echo_solver_progress and match:
                iteration = int(match.group(1))
                if iteration <= 10 or iteration % 20 == 0:
                    print(f"[{name}] {line.strip()}", flush=True)
        returncode = process.wait()
    if returncode:
        raise RuntimeError(
            f"{name} failed with exit code {returncode}; see {log_path}"
        )


def new_transcript(previous: set[Path]) -> Path:
    candidates = [path for path in ROOT.glob("fluent-*.trn") if path not in previous]
    if not candidates:
        raise RuntimeError("Fluent solve produced no new transcript")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def skipped_stage(name: str, artifact: Path, run_dir: Path) -> None:
    (run_dir / f"{name}.log").write_text(
        f"RESUME_SKIP\nexisting artifact: {artifact}\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-json", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--mesh-tier", choices=("coarse", "paper"), required=True)
    parser.add_argument("--mesh-cores", type=int, default=8)
    parser.add_argument("--solve-cores", type=int, default=10)
    parser.add_argument("--post-cores", type=int, default=2)
    parser.add_argument("--iters", type=int)
    parser.add_argument("--startup-iters", type=int)
    parser.add_argument("--repair-passes", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tier = args.mesh_tier
    iters = args.iters if args.iters is not None else DEFAULT_ITERS[tier]
    startup_iters = (
        args.startup_iters
        if args.startup_iters is not None
        else DEFAULT_STARTUP_ITERS[tier]
    )
    repair_passes = (
        args.repair_passes
        if args.repair_passes is not None
        else DEFAULT_REPAIR_PASSES[tier]
    )
    if iters <= 0 or not 0 <= startup_iters <= iters or repair_passes < 0:
        parser.error("require iters > 0, 0 <= startup-iters <= iters, repair-passes >= 0")

    design_path = Path(args.design_json).resolve()
    design = json.loads(design_path.read_text(encoding="utf-8"))
    required = {
        "SS1_s", "SS2_s", "PS1_s", "PS2_s",
        "suction_angle_deg", "pressure_angle_deg",
    }
    missing = sorted(required - design.keys())
    if missing:
        raise KeyError(f"design is missing variables: {missing}")
    diameter_mm, span_count = resolve_hole_geometry(design)

    run_dir = Path(args.run_dir).resolve()
    result_path = Path(args.result_json).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    geometry_prefix = run_dir / "c3x"
    mesh_prefix = run_dir / f"c3x_{tier}"
    raw_mesh = mesh_prefix.with_suffix(".msh.h5")
    active_mesh = raw_mesh
    setup_case = run_dir / f"c3x_{tier}_setup.cas.h5"
    solution_prefix = run_dir / f"c3x_{tier}_iter{iters}"
    solution_case = solution_prefix.with_suffix(".cas.h5")
    solution_data = solution_prefix.with_suffix(".dat.h5")
    post_dir = run_dir / f"post_iter{iters}"
    status_path = run_dir / "pipeline_status.json"
    status = {
        "status": "running",
        "started_utc": utc_now(),
        "mesh_tier": tier,
        "iterations": iters,
        "startup_iterations": startup_iters,
        "repair_passes": repair_passes,
        "design_json": str(design_path),
        "diameter_mm": diameter_mm,
        "span_count": span_count,
        "result_json": str(result_path),
        "dry_run": args.dry_run,
    }
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")

    try:
        geometry_command = [
            python, "scripts/build_c3x_workbench_case.py",
            "--design", str(BASE_DESIGN),
            "--template", str(TEMPLATE),
            "--targets", str(TARGETS),
            "--out-prefix", str(geometry_prefix),
            "--ss1-s", str(design["SS1_s"]),
            "--ss2-s", str(design["SS2_s"]),
            "--ps1-s", str(design["PS1_s"]),
            "--ps2-s", str(design["PS2_s"]),
            "--suction-angle", str(design["suction_angle_deg"]),
            "--pressure-angle", str(design["pressure_angle_deg"]),
            "--diameter-mm", str(diameter_mm),
            "--span-count", str(span_count),
        ]
        if args.resume and geometry_prefix.with_suffix(".scdoc").is_file():
            skipped_stage("geometry", geometry_prefix.with_suffix(".scdoc"), run_dir)
        else:
            run_stage("geometry", geometry_command, run_dir, args.dry_run)
        mesh_command = [
            python, "scripts/run_fluent_native_cad_mesh.py",
            "--cad", str(geometry_prefix.with_suffix(".scdoc")),
            "--tier", tier, "--tiers", str(TIERS),
            "--cores", str(args.mesh_cores), "--out-prefix", str(mesh_prefix),
        ]
        if args.resume and raw_mesh.is_file():
            skipped_stage("mesh", raw_mesh, run_dir)
        else:
            run_stage("mesh", mesh_command, run_dir, args.dry_run)

        for index in range(1, repair_passes + 1):
            repaired_mesh = run_dir / f"c3x_{tier}_repaired{index}.msh.h5"
            repair_command = [
                python, "scripts/repair_fluent_mesh_quality.py",
                "--mesh", str(active_mesh), "--out-mesh", str(repaired_mesh),
                "--out-json", str(run_dir / f"repair_{index}.json"),
                "--quality-limit", "0.05", "--cores", str(args.mesh_cores),
                "--precision", "single",
            ]
            if args.resume and repaired_mesh.is_file():
                skipped_stage(f"repair_{index}", repaired_mesh, run_dir)
            else:
                run_stage(f"repair_{index}", repair_command, run_dir, args.dry_run)
            active_mesh = repaired_mesh

        setup_command = [
            python, "scripts/run_workbench_film_setup.py",
            "--case-in", str(active_mesh), "--case-out", str(setup_case),
            "--simulation-case", "nasa_44344_validation",
            "--cores", str(args.solve_cores), "--precision", "single",
        ]
        if args.resume and setup_case.is_file():
            skipped_stage("setup", setup_case, run_dir)
        else:
            run_stage("setup", setup_command, run_dir, args.dry_run)
        transcripts_before = set(ROOT.glob("fluent-*.trn"))
        solve_command = [
            python, "scripts/run_workbench_film_iterate.py",
            "--case", str(setup_case), "--iters", str(iters),
            "--startup-iters", str(startup_iters), "--initialization", "hybrid",
            "--out-prefix", str(solution_prefix), "--cores", str(args.solve_cores),
            "--precision", "single", "--energy-urf", "0.8",
            "--temperature-min-k", "300", "--temperature-max-k", "1000",
        ]
        transcript_copy = run_dir / "fluent_solve.trn"
        if args.resume and solution_case.is_file() and solution_data.is_file() and transcript_copy.is_file():
            skipped_stage("solve", solution_data, run_dir)
        else:
            run_stage(
                "solve",
                solve_command,
                run_dir,
                args.dry_run,
                echo_solver_progress=True,
            )
        if args.dry_run:
            transcript_copy.write_text("DRY_RUN\n", encoding="utf-8")
        elif not (args.resume and transcript_copy.is_file()):
            transcript = new_transcript(transcripts_before)
            shutil.copy2(transcript, transcript_copy)
            status["fluent_transcript_source"] = str(transcript)

        post_command = [
            python, "scripts/export_workbench_film_results.py",
            "--case", str(solution_case), "--data", str(solution_data),
            "--out-dir", str(post_dir), "--log", str(transcript_copy),
            "--simulation-case", "nasa_44344_validation",
            "--cores", str(args.post_cores), "--precision", "single",
            "--hole-diameter-mm", str(diameter_mm),
            "--protected-pressure-xmin", "0.26530",
            "--protected-suction-xmin", "0.37638",
        ]
        if args.resume and (post_dir / "bo_summary.json").is_file():
            skipped_stage("post", post_dir / "bo_summary.json", run_dir)
        else:
            run_stage("post", post_command, run_dir, args.dry_run)
        contract_command = [
            python, "scripts/write_optimization_result.py",
            "--post-dir", str(post_dir), "--baseline", str(BASELINES[tier]),
            "--out", str(result_path),
        ]
        if args.resume and result_path.is_file():
            skipped_stage("contract", result_path, run_dir)
        else:
            run_stage("contract", contract_command, run_dir, args.dry_run)
        visual_command = [
            python, "scripts/plot_optimization_iteration.py",
            "--layout", str(geometry_prefix.with_name(geometry_prefix.name + "_layout.png")),
            "--post-dir", str(post_dir), "--result", str(result_path),
            "--out-dir", str(run_dir / "visuals"),
            "--trial-label", f"{tier} iteration {iters}",
        ]
        visual_manifest = run_dir / "visuals" / "visual_manifest.json"
        if args.resume and visual_manifest.is_file():
            skipped_stage("visuals", visual_manifest, run_dir)
        else:
            run_stage("visuals", visual_command, run_dir, args.dry_run)
        status.update({"status": "dry_run_ok" if args.dry_run else "ok", "finished_utc": utc_now()})
        status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        status.update({
            "status": "error", "finished_utc": utc_now(),
            "error": str(exc), "traceback": traceback.format_exc(),
        })
        status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(status["traceback"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
