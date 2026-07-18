"""Evaluation backends for synthetic development and external CFD pipelines."""
from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .config import OptimizationConfig
from .prior import FilmCoolingPrior


@dataclass(frozen=True)
class EvaluationResult:
    objective: float
    constraints: dict[str, float]
    metrics: dict[str, Any]


class DemoEvaluator:
    """Deterministic synthetic plant for exercising the full controller."""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.prior = FilmCoolingPrior(config.prior)
        self.delay = float(config.evaluator.get("demo_delay_seconds", 0.15))

    def evaluate(
        self,
        design: dict[str, float | int],
        fidelity: str,
        run_dir: Path,
        log: Callable[[str], None],
    ) -> EvaluationResult:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "design.json").write_text(
            json.dumps(design, indent=2), encoding="utf-8"
        )
        fidelity_spec = self.config.fidelity(fidelity)
        if fidelity_spec.kind == "knowledge":
            objective = self.prior(design)
            result = EvaluationResult(
                objective=objective,
                constraints={},
                metrics={
                    "physics_prior": objective,
                    "fidelity_level": fidelity_spec.level,
                    "information_kind": "knowledge",
                    "synthetic": True,
                },
            )
            log("demo evaluator: deterministic L1 knowledge")
            self._write_result(run_dir, result)
            return result
        log("demo evaluator: correlation prior + hidden CFD discrepancy")
        time.sleep(self.delay)
        prior = self.prior(design)
        ss_mid = 0.5 * (float(design["SS1_s"]) + float(design["SS2_s"]))
        ps_mid = 0.5 * (float(design["PS1_s"]) + float(design["PS2_s"]))
        interaction = (
            0.055 * np.exp(-((ss_mid - 0.255) / 0.018) ** 2)
            + 0.040 * np.exp(-((ps_mid - 0.222) / 0.018) ** 2)
            - 0.018 * ((float(design["suction_angle_deg"]) - 34.0) / 10.0) ** 2
        )
        level = fidelity_spec.level
        digest = hashlib.sha256(
            json.dumps([design, fidelity], sort_keys=True).encode("utf-8")
        ).digest()
        deterministic_noise = (int.from_bytes(digest[:4], "little") / 2**32 - 0.5)
        fidelity_bias = -0.025 * (1.0 - level)
        eta = float(np.clip(prior + interaction + fidelity_bias + 0.004 * deterministic_noise, 0.0, 0.95))
        diameter = float(design.get("diameter_mm", 0.99))
        count = float(design.get("span_count", 5))
        mass_ratio = float((diameter / 0.99) ** 2 * count / 5.0)
        loss_ratio = float(
            0.985 + 0.020 * mass_ratio
            + 0.006 * abs(float(design["pressure_angle_deg"]) - 30.0) / 10.0
        )
        result = EvaluationResult(
            objective=eta,
            constraints={"coolant_mass_ratio": mass_ratio, "loss_ratio": loss_ratio},
            metrics={
                "physics_prior": prior,
                "fidelity_level": level,
                "synthetic": True,
            },
        )
        self._write_result(run_dir, result)
        return result

    @staticmethod
    def _write_result(run_dir: Path, result: EvaluationResult) -> None:
        (run_dir / "result.json").write_text(
            json.dumps(
                {
                    "objective": result.objective,
                    "constraints": result.constraints,
                    "metrics": result.metrics,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


class CommandEvaluator:
    """Run configured CAD/mesh/solver/post stages and read a result contract."""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.root = Path(__file__).resolve().parents[2]
        self.prior = FilmCoolingPrior(config.prior)

    def evaluate(
        self,
        design: dict[str, float | int],
        fidelity: str,
        run_dir: Path,
        log: Callable[[str], None],
    ) -> EvaluationResult:
        run_dir.mkdir(parents=True, exist_ok=True)
        design_path = run_dir / "design.json"
        result_path = run_dir / "result.json"
        design_path.write_text(json.dumps(design, indent=2), encoding="utf-8")
        fidelity_spec = self.config.fidelity(fidelity)
        if fidelity_spec.kind == "knowledge":
            objective = self.prior(design)
            payload = {
                "objective": objective,
                "constraints": {},
                "metrics": {
                    "physics_prior": objective,
                    "information_kind": "knowledge",
                },
            }
            result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            log("evaluated deterministic L1 knowledge; no external CFD stage")
            return EvaluationResult(objective=objective, constraints={}, metrics=payload["metrics"])
        resources = self.config.evaluator.get("resources", {})
        tier_resources = resources.get(fidelity_spec.mesh_tier, {})
        context = {
            **design,
            "fidelity": fidelity,
            "mesh_tier": fidelity_spec.mesh_tier,
            "run_dir": str(run_dir),
            "design_json": str(design_path),
            "result_json": str(result_path),
            "python": str(self.root / ".venv" / "python.exe"),
            "root": str(self.root),
            "mesh_cores": int(tier_resources.get("mesh_cores", 8)),
            "solve_cores": int(tier_resources.get("solve_cores", 10)),
            "post_cores": int(tier_resources.get("post_cores", 2)),
        }
        for stage in self.config.evaluator.get("stages", []):
            name = stage["name"]
            command = stage["command"].format_map(context)
            log(f"stage {name}: {command}")
            stage_log = run_dir / f"{name}.log"
            process = subprocess.Popen(
                command,
                cwd=self.root,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            timed_out = threading.Event()

            def terminate_on_timeout() -> None:
                timed_out.set()
                try:
                    process.kill()
                except OSError:
                    pass

            timer = threading.Timer(
                float(stage.get("timeout_seconds", 86400)), terminate_on_timeout
            )
            timer.start()
            try:
                with stage_log.open("w", encoding="utf-8") as stream:
                    assert process.stdout is not None
                    for line in process.stdout:
                        stream.write(line)
                        print(line, end="", flush=True)
                returncode = process.wait()
            finally:
                timer.cancel()
            if timed_out.is_set():
                raise RuntimeError(
                    f"stage {name} exceeded timeout; see {stage_log}"
                )
            if returncode:
                raise RuntimeError(
                    f"stage {name} failed with exit code {returncode}; see {stage_log}"
                )
        if not result_path.is_file():
            raise FileNotFoundError(
                f"pipeline did not produce result contract: {result_path}"
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return EvaluationResult(
            objective=float(payload["objective"]),
            constraints={key: float(value) for key, value in payload.get("constraints", {}).items()},
            metrics=dict(payload.get("metrics", {})),
        )


def build_evaluator(config: OptimizationConfig):
    evaluator_type = config.evaluator.get("type", "demo")
    if evaluator_type == "demo":
        return DemoEvaluator(config)
    if evaluator_type == "command":
        return CommandEvaluator(config)
    raise ValueError(f"unknown evaluator type: {evaluator_type}")
