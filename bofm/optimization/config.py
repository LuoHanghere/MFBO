"""Typed configuration and design-vector transformations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass(frozen=True)
class VariableSpec:
    name: str
    label: str
    lower: float
    upper: float
    baseline: float
    kind: str = "continuous"
    unit: str = ""

    def decode(self, unit_value: float) -> float | int:
        value = self.lower + float(np.clip(unit_value, 0.0, 1.0)) * (
            self.upper - self.lower
        )
        return int(round(value)) if self.kind == "integer" else float(value)

    def encode(self, value: float) -> float:
        return float((value - self.lower) / (self.upper - self.lower))


@dataclass(frozen=True)
class FidelitySpec:
    name: str
    level: float
    relative_cost: float
    mesh_tier: str
    kind: str = "cfd"


@dataclass(frozen=True)
class ConstraintSpec:
    name: str
    upper: float
    label: str


@dataclass(frozen=True)
class OptimizationConfig:
    name: str
    variables: tuple[VariableSpec, ...]
    fidelities: tuple[FidelitySpec, ...]
    constraints: tuple[ConstraintSpec, ...]
    objective_name: str
    objective_label: str
    maximize: bool
    initial_designs: int
    candidate_pool: int
    seed: int
    budget: float
    database: Path
    run_root: Path
    evaluator: dict[str, Any]
    prior: dict[str, Any]
    raw: dict[str, Any]

    @property
    def dimension(self) -> int:
        return len(self.variables)

    @property
    def baseline(self) -> dict[str, float | int]:
        return {v.name: v.decode(v.encode(v.baseline)) for v in self.variables}

    def decode(self, unit_vector: np.ndarray) -> dict[str, float | int]:
        return {
            spec.name: spec.decode(float(value))
            for spec, value in zip(self.variables, unit_vector)
        }

    def encode(self, design: dict[str, float]) -> np.ndarray:
        return np.asarray(
            [spec.encode(float(design[spec.name])) for spec in self.variables],
            dtype=float,
        )

    def fidelity(self, name: str) -> FidelitySpec:
        return next(item for item in self.fidelities if item.name == name)


def load_optimization_config(path: str | Path) -> OptimizationConfig:
    path = Path(path).resolve()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = path.parents[1] if path.parent.name == "configs" else path.parent

    variables = tuple(
        VariableSpec(
            name=item["name"],
            label=item.get("label", item["name"]),
            lower=float(item["bounds"][0]),
            upper=float(item["bounds"][1]),
            baseline=float(item["baseline"]),
            kind=item.get("kind", "continuous"),
            unit=item.get("unit", ""),
        )
        for item in raw["variables"]
    )
    fidelities = tuple(
        FidelitySpec(
            name=item["name"],
            level=float(item["level"]),
            relative_cost=float(item["relative_cost"]),
            mesh_tier=item.get("mesh_tier", item["name"]),
            kind=item.get("kind", "cfd"),
        )
        for item in raw["fidelities"]
    )
    constraints = tuple(
        ConstraintSpec(
            name=item["name"],
            upper=float(item["upper"]),
            label=item.get("label", item["name"]),
        )
        for item in raw.get("constraints", [])
    )
    for spec in variables:
        if spec.lower >= spec.upper:
            raise ValueError(f"invalid bounds for {spec.name}")
        if not spec.lower <= spec.baseline <= spec.upper:
            raise ValueError(f"baseline outside bounds for {spec.name}")

    def resolve(value: str) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else (root / candidate).resolve()

    return OptimizationConfig(
        name=raw["name"],
        variables=variables,
        fidelities=fidelities,
        constraints=constraints,
        objective_name=raw["objective"]["name"],
        objective_label=raw["objective"].get("label", raw["objective"]["name"]),
        maximize=bool(raw["objective"].get("maximize", True)),
        initial_designs=int(raw["optimizer"].get("initial_designs", 8)),
        candidate_pool=int(raw["optimizer"].get("candidate_pool", 2048)),
        seed=int(raw["optimizer"].get("seed", 20260711)),
        budget=float(raw["optimizer"].get("equivalent_high_fidelity_budget", 20.0)),
        database=resolve(raw["storage"]["database"]),
        run_root=resolve(raw["storage"]["run_root"]),
        evaluator=dict(raw.get("evaluator", {"type": "demo"})),
        prior=dict(raw.get("physics_prior", {})),
        raw=raw,
    )
