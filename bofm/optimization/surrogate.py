"""Physics-informed, constrained, cost-aware Bayesian proposal policy."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize
from scipy.special import ndtr
from scipy.stats import qmc

from .config import OptimizationConfig
from .feasibility import build_geometry_gate
from .prior import FilmCoolingPrior


def _matern52(a: np.ndarray, b: np.ndarray, length: np.ndarray) -> np.ndarray:
    distance = np.sqrt(
        np.maximum(
            ((a[:, None, :] - b[None, :, :]) ** 2 / length[None, None, :] ** 2).sum(axis=2),
            0.0,
        )
    )
    root5 = np.sqrt(5.0) * distance
    return (1.0 + root5 + 5.0 * distance**2 / 3.0) * np.exp(-root5)


class GaussianProcess:
    """Small exact GP suited to the low-data online BO regime."""

    def __init__(self, x: np.ndarray, y: np.ndarray):
        self.x = np.asarray(x, dtype=float)
        self.mean = float(np.mean(y))
        self.scale = max(float(np.std(y)), 1e-6)
        self.y = (np.asarray(y, dtype=float) - self.mean) / self.scale
        initial = np.r_[np.full(self.x.shape[1], np.log(0.28)), np.log(1e-4)]

        def nll(theta: np.ndarray) -> float:
            length = np.exp(theta[:-1])
            noise = np.exp(theta[-1])
            kernel = _matern52(self.x, self.x, length)
            kernel.flat[:: len(kernel) + 1] += noise + 1e-8
            try:
                factor = cho_factor(kernel, lower=True, check_finite=False)
                alpha = cho_solve(factor, self.y, check_finite=False)
            except np.linalg.LinAlgError:
                return 1e12
            return float(
                0.5 * self.y @ alpha
                + np.log(np.diag(factor[0])).sum()
                + 0.5 * len(self.y) * np.log(2.0 * np.pi)
            )

        result = minimize(
            nll,
            initial,
            method="L-BFGS-B",
            bounds=[(np.log(0.04), np.log(3.0))] * self.x.shape[1]
            + [(np.log(1e-7), np.log(0.2))],
            options={"maxiter": 80},
        )
        self.length = np.exp(result.x[:-1])
        self.noise = float(np.exp(result.x[-1]))
        kernel = _matern52(self.x, self.x, self.length)
        kernel.flat[:: len(kernel) + 1] += self.noise + 1e-8
        self.factor = cho_factor(kernel, lower=True, check_finite=False)
        self.alpha = cho_solve(self.factor, self.y, check_finite=False)

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(x, dtype=float)
        cross = _matern52(x, self.x, self.length)
        mean = cross @ self.alpha
        solved = cho_solve(self.factor, cross.T, check_finite=False)
        variance = np.maximum(1.0 - np.sum(cross * solved.T, axis=1), 1e-10)
        return self.mean + self.scale * mean, self.scale * np.sqrt(variance)


@dataclass(frozen=True)
class Proposal:
    design: dict[str, float | int]
    fidelity: str
    source: str
    predicted: dict[str, float]


class PhysicsInformedPolicy:
    """Ask policy: LHS startup, then residual-GP constrained EI per unit cost."""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.prior = FilmCoolingPrior(config.prior)
        self.prior_enabled = bool(config.prior.get("enabled", True))
        self.cfd_fidelities = tuple(
            fidelity for fidelity in config.fidelities if fidelity.kind == "cfd"
        )
        if not self.cfd_fidelities:
            raise ValueError("optimization requires at least one CFD fidelity")
        self.geometry_gate = build_geometry_gate(
            config.raw.get("optimizer", {}).get("geometry_gate")
        )
        self.startup_designs = self._load_startup_designs()

    def _load_startup_designs(self) -> tuple[dict[str, float | int], ...]:
        value = self.config.raw.get("optimizer", {}).get("initial_design_file")
        if not value:
            return ()
        path = Path(value)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("designs", payload) if isinstance(payload, dict) else payload
        resolved = []
        for record in records:
            design = record.get("design", record)
            encoded = self.config.encode(design)
            if np.any(encoded < -1e-12) or np.any(encoded > 1.0 + 1e-12):
                raise ValueError(f"startup design outside configured bounds: {design}")
            resolved.append(self.config.decode(encoded))
        return tuple(resolved)

    def propose(self, trials: list[dict]) -> Proposal:
        completed = [trial for trial in trials if trial["status"] == "completed"]
        if not trials:
            return Proposal(self.config.baseline, self.config.fidelities[0].name, "baseline", {})
        spent = sum(float(item["relative_cost"]) for item in completed)
        for fidelity in self.cfd_fidelities:
            seen = any(item["fidelity"] == fidelity.name for item in trials)
            if not seen and spent + fidelity.relative_cost <= self.config.budget + 1e-12:
                return Proposal(self.config.baseline, fidelity.name, "paired_baseline", {})
        low_name = self.cfd_fidelities[0].name
        low_completed = [item for item in completed if item["fidelity"] == low_name]
        if len(low_completed) < self.config.initial_designs:
            for design in self.startup_designs:
                point = self.config.encode(design)
                if self._hard_feasible(design) and self._not_duplicate(
                    point, low_name, trials
                ):
                    return Proposal(design, low_name, "stratified_startup", {})
            sampler = qmc.LatinHypercube(d=self.config.dimension, seed=self.config.seed)
            points = sampler.random(self.config.initial_designs * 20)
            index = min(max(len(low_completed) - 1, 0), len(points) - 1)
            design = self._next_unique(points[index:], trials)
            return Proposal(design, low_name, "lhs", {})
        return self._bayesian_proposal(completed, trials)

    def _next_unique(self, points: np.ndarray, trials: list[dict]) -> dict[str, float | int]:
        existing = [self.config.encode(item["design"]) for item in trials]
        for point in points:
            design = self.config.decode(point)
            if self._hard_feasible(design) and all(
                np.linalg.norm(point - old) > 1e-5 for old in existing
            ):
                return design
        rng = np.random.default_rng(self.config.seed + len(trials))
        while True:
            point = rng.random(self.config.dimension)
            design = self.config.decode(point)
            if self._hard_feasible(design):
                return design

    def _bayesian_proposal(self, completed: list[dict], all_trials: list[dict]) -> Proposal:
        cfd_completed = [
            item for item in completed
            if self.config.fidelity(item["fidelity"]).kind == "cfd"
        ]
        x_design = np.vstack([self.config.encode(item["design"]) for item in cfd_completed])
        fidelity_level = np.asarray(
            [self.config.fidelity(item["fidelity"]).level for item in cfd_completed]
        )[:, None]
        x = np.hstack([x_design, fidelity_level])
        prior_anchor = self._prior_anchor(cfd_completed)
        prior_values = np.asarray([
            self._prior_mean(item["design"], prior_anchor) for item in cfd_completed
        ])
        objective = np.asarray([float(item["objective"]) for item in cfd_completed])
        if not self.config.maximize:
            objective = -objective
            prior_values = -prior_values
        objective_gp = GaussianProcess(x, objective - prior_values)

        constraint_gps = {}
        for constraint in self.config.constraints:
            values = np.asarray(
                [
                    float(item["constraints"].get(constraint.name, np.nan))
                    for item in cfd_completed
                ]
            )
            valid = np.isfinite(values)
            if valid.sum() >= 3:
                constraint_gps[constraint.name] = GaussianProcess(
                    x[valid], constraint.upper - values[valid]
                )

        target_name = self.cfd_fidelities[-1].name
        feasible_values = [
            value
            for value, trial in zip(objective, cfd_completed)
            if trial["fidelity"] == target_name and self._observed_feasible(trial)
        ]
        if not feasible_values:
            feasible_values = [
                value for value, trial in zip(objective, cfd_completed)
                if self._observed_feasible(trial)
            ]
        incumbent = max(feasible_values) if feasible_values else float(np.max(objective))
        sampler = qmc.Sobol(d=self.config.dimension, scramble=True, seed=self.config.seed + len(all_trials))
        exponent = int(np.ceil(np.log2(max(self.config.candidate_pool, 2))))
        candidates = sampler.random_base2(exponent)[: self.config.candidate_pool]
        decoded = [self.config.decode(point) for point in candidates]
        valid = np.asarray([self._hard_feasible(design) for design in decoded])
        candidates = candidates[valid]
        decoded = [design for design, keep in zip(decoded, valid) if keep]
        if not decoded:
            raise RuntimeError("candidate pool contains no geometrically feasible design")

        failed = [
            item for item in all_trials
            if item["status"] == "failed"
            and self.config.fidelity(item["fidelity"]).kind == "cfd"
        ]
        failed_x = np.vstack([self.config.encode(item["design"]) for item in failed]) if failed else None
        best = None
        for fidelity in self.cfd_fidelities:
            query = np.hstack([candidates, np.full((len(candidates), 1), fidelity.level)])
            residual_mean, residual_sigma = objective_gp.predict(query)
            physical = np.asarray([
                self._prior_mean(design, prior_anchor) for design in decoded
            ])
            if not self.config.maximize:
                physical = -physical
            mean = physical + residual_mean
            prior_sigma = self._prior_sigma(candidates, cfd_completed)
            sigma = np.sqrt(residual_sigma**2 + prior_sigma**2)
            z = (mean - incumbent) / np.maximum(sigma, 1e-12)
            ei = (mean - incumbent) * ndtr(z) + sigma * np.exp(-0.5 * z**2) / np.sqrt(2.0 * np.pi)
            probability = np.ones(len(query))
            for gp in constraint_gps.values():
                g_mean, g_sigma = gp.predict(query)
                probability *= ndtr(g_mean / np.maximum(g_sigma, 1e-12))
            failure_avoidance = np.ones(len(query))
            if failed_x is not None:
                nearest = np.sqrt(((candidates[:, None, :] - failed_x[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
                failure_avoidance = 1.0 - np.exp(-(nearest / 0.08) ** 2)
            prior_weight = self._prior_acquisition_weight(decoded, cfd_completed)
            acquisition = (
                (ei + 0.02 * sigma) * probability * failure_avoidance
                * prior_weight / fidelity.relative_cost
            )
            for index in np.argsort(acquisition)[::-1]:
                if self._not_duplicate(candidates[index], fidelity.name, all_trials):
                    candidate = (
                        float(acquisition[index]),
                        decoded[index],
                        fidelity.name,
                        {
                            "mean": float(mean[index]),
                            "sigma": float(sigma[index]),
                            "residual_sigma": float(residual_sigma[index]),
                            "prior_sigma": float(prior_sigma[index]),
                            "prior_weight": float(prior_weight[index]),
                            "ei": float(ei[index]),
                            "p_feasible": float(probability[index]),
                            "acquisition_per_cost": float(acquisition[index]),
                            "physics_prior": float(physical[index]),
                        },
                    )
                    if best is None or candidate[0] > best[0]:
                        best = candidate
                    break
        if best is None:
            raise RuntimeError("unable to generate a non-duplicate BO proposal")
        _, design, fidelity, predicted = best
        source = "physics_constrained_ei" if self.prior_enabled else "standard_constrained_ei"
        return Proposal(design, fidelity, source, predicted)

    def _physics_prior(self, design: dict[str, float | int]) -> float:
        return self.prior(design) if self.prior_enabled else 0.0

    def _prior_anchor(self, completed: list[dict]) -> float:
        if not self.prior_enabled:
            return 0.0
        baseline = self.config.encode(self.config.baseline)
        target = self.cfd_fidelities[-1].name
        ordered = sorted(
            completed,
            key=lambda item: (
                item["fidelity"] != target,
                np.linalg.norm(self.config.encode(item["design"]) - baseline),
            ),
        )
        return float(ordered[0]["objective"]) if ordered else self.prior(self.config.baseline)

    def _prior_mean(self, design: dict[str, float | int], anchor: float) -> float:
        if not self.prior_enabled:
            return 0.0
        calibration = self.config.prior.get("calibration", {})
        scale = float(calibration.get("mean_scale", 1.0))
        raw_baseline = self.prior(self.config.baseline)
        return float(anchor + scale * (self.prior(design) - raw_baseline))

    def _prior_sigma(self, points: np.ndarray, completed: list[dict]) -> np.ndarray:
        if not self.prior_enabled:
            return np.zeros(len(points))
        settings = self.config.prior.get("uncertainty", {})
        baseline_sigma = max(float(settings.get("baseline_sigma", 0.0)), 0.0)
        distance_sigma = max(float(settings.get("distance_sigma", 0.0)), 0.0)
        decay_power = max(float(settings.get("decay_power", 0.5)), 0.0)
        baseline = self.config.encode(self.config.baseline)
        distance = np.linalg.norm(points - baseline[None, :], axis=1) / np.sqrt(self.config.dimension)
        target = self.cfd_fidelities[-1].name
        high_count = sum(item["fidelity"] == target for item in completed)
        return (baseline_sigma + distance_sigma * distance) / (1.0 + high_count) ** decay_power

    def _prior_acquisition_weight(
        self, designs: list[dict[str, float | int]], completed: list[dict]
    ) -> np.ndarray:
        if not self.prior_enabled:
            return np.ones(len(designs))
        settings = self.config.prior.get("acquisition", {})
        if settings.get("mode", "none") != "pi_weight":
            return np.ones(len(designs))
        raw = np.asarray([self.prior(design) for design in designs])
        spread = max(float(np.std(raw)), 1e-12)
        normalized = (raw - float(np.mean(raw))) / spread
        target = self.cfd_fidelities[-1].name
        high_count = sum(item["fidelity"] == target for item in completed)
        beta = max(float(settings.get("initial_beta", 1.0)), 0.0) / (
            1.0 + max(float(settings.get("high_fidelity_decay", 0.25)), 0.0) * high_count
        )
        floor = float(np.clip(settings.get("minimum_weight", 0.10), 1e-6, 1.0))
        relative = np.exp(np.clip(beta * (normalized - np.max(normalized)), -50.0, 0.0))
        return floor + (1.0 - floor) * relative

    def _observed_feasible(self, trial: dict) -> bool:
        return all(
            float(trial["constraints"].get(spec.name, np.inf)) <= spec.upper
            for spec in self.config.constraints
        )

    def _hard_feasible(self, design: dict[str, float | int]) -> bool:
        basic = (
            float(design["SS2_s"]) - float(design["SS1_s"]) >= 0.005
            and float(design["PS2_s"]) - float(design["PS1_s"]) >= 0.005
        )
        return basic and (self.geometry_gate is None or self.geometry_gate(design))

    def _not_duplicate(self, point: np.ndarray, fidelity: str, trials: list[dict]) -> bool:
        return all(
            item["fidelity"] != fidelity
            or np.linalg.norm(point - self.config.encode(item["design"])) > 1e-5
            for item in trials
        )
