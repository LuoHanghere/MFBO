from __future__ import annotations

import json
from pathlib import Path
import time
from dataclasses import replace

import numpy as np

from bofm.optimization.config import load_optimization_config
from bofm.optimization.engine import EngineState, OptimizationEngine
from bofm.optimization.evaluator import DemoEvaluator
from bofm.optimization.feasibility import C3XDownstreamGeometryGate, build_geometry_gate
from bofm.optimization.prior import FilmCoolingPrior
from bofm.optimization.storage import ExperimentStore
from bofm.optimization.surrogate import GaussianProcess, PhysicsInformedPolicy
from scripts.run_nasa_optimization_trial import resolve_hole_geometry
from scripts.build_c3x_downstream_layout import build_layout


def config():
    return load_optimization_config("configs/c3x_optimization.yaml")


def test_config_round_trip_and_integer_decode():
    cfg = config()
    encoded = cfg.encode(cfg.baseline)
    decoded = cfg.decode(encoded)
    assert decoded["span_count"] == 5
    assert np.allclose(cfg.encode(decoded), encoded)


def test_prior_is_finite_and_design_sensitive():
    cfg = config()
    prior = FilmCoolingPrior(cfg.prior)
    baseline = prior(cfg.baseline)
    changed = dict(cfg.baseline, suction_angle_deg=45.0)
    assert 0.0 < baseline < 1.0
    assert prior(changed) != baseline


def test_store_round_trip(tmp_path):
    store = ExperimentStore(tmp_path / "ledger.sqlite3")
    trial_id = store.create_trial({"x": 0.5}, "L1", "test", 0.1, {"mean": 1.0})
    store.mark_running(trial_id, tmp_path / "trial")
    store.complete(trial_id, 0.4, {"g": 0.9}, {"ok": True})
    trial = store.trials()[0]
    assert trial["status"] == "completed"
    assert trial["objective"] == 0.4
    assert trial["predicted"]["mean"] == 1.0


def test_exact_gp_interpolates_training_trend():
    x = np.linspace(0.0, 1.0, 8)[:, None]
    y = np.sin(2.0 * np.pi * x[:, 0])
    gp = GaussianProcess(x, y)
    mean, sigma = gp.predict(x)
    assert np.max(np.abs(mean - y)) < 0.08
    assert np.all(sigma >= 0.0)


def test_policy_starts_with_baseline():
    cfg = config()
    proposal = PhysicsInformedPolicy(cfg).propose([])
    assert proposal.source == "baseline"
    assert proposal.design == cfg.baseline
    assert proposal.fidelity == "L1"


def test_knowledge_level_is_deterministic_prior(tmp_path):
    cfg = config()
    result = DemoEvaluator(cfg).evaluate(cfg.baseline, "L1", tmp_path, lambda _: None)
    assert result.objective == FilmCoolingPrior(cfg.prior)(cfg.baseline)
    assert result.constraints == {}
    assert result.metrics["information_kind"] == "knowledge"


def test_standard_mfbo_disables_prior_and_has_two_cfd_levels():
    cfg = load_optimization_config("configs/c3x_nasa_standard_mfbo.yaml")
    policy = PhysicsInformedPolicy(cfg)
    assert not policy.prior_enabled
    assert [fidelity.name for fidelity in policy.cfd_fidelities] == ["L2", "L3"]


def test_nasa_8d_standard_mfbo_uses_stratified_startup_queue():
    cfg = load_optimization_config("configs/c3x_nasa_standard_mfbo_8d.yaml")
    policy = PhysicsInformedPolicy(cfg)
    assert cfg.dimension == 8
    assert not policy.prior_enabled
    assert len(policy.startup_designs) == 12
    trials = [
        {
            "id": index,
            "fidelity": fidelity,
            "status": "completed",
            "objective": 0.65,
            "relative_cost": 0.2 if fidelity == "L2" else 1.0,
            "design": cfg.baseline,
            "constraints": {"coolant_mass_ratio": 1.0},
        }
        for index, fidelity in enumerate(("L2", "L3"), start=1)
    ]
    proposal = policy.propose(trials)
    assert proposal.source == "stratified_startup"
    assert proposal.fidelity == "L2"
    assert proposal.design == policy.startup_designs[0]
    assert proposal.design["span_count"] == 4


def test_nasa_runner_resolves_legacy_and_8d_hole_geometry():
    assert resolve_hole_geometry({}) == (0.99, 5)
    assert resolve_hole_geometry({"diameter_mm": 1.05, "span_count": 7}) == (1.05, 7)


def test_nasa_8d_layout_uses_requested_span_count():
    base = load_optimization_config("configs/c3x_nasa_standard_mfbo_8d.yaml").baseline
    design = json.loads(
        Path("runs/nasa_44344/geometry/c3x_nasa44344_periodic_v2_design.json")
        .read_text(encoding="utf-8")
    )
    design["geometry"]["diameter_mm"] = base["diameter_mm"]
    design["geometry"]["span_count"] = 4
    layout = build_layout(design)
    assert len(layout["rows"]) == 4
    assert layout["geometry"]["span_count_per_row"] == 4
    assert sum(len(row["cylinder_markers"]) for row in layout["rows"]) == 16


def test_pi_prior_is_l3_anchored_and_acquisition_keeps_full_support():
    cfg = load_optimization_config("configs/c3x_nasa_pimfbo.yaml")
    policy = PhysicsInformedPolicy(cfg)
    completed = [
        {
            "fidelity": "L3",
            "objective": 0.65,
            "design": cfg.baseline,
            "constraints": {"coolant_mass_ratio": 1.0, "loss_ratio": 1.0},
        }
    ]
    anchor = policy._prior_anchor(completed)
    assert policy._prior_mean(cfg.baseline, anchor) == 0.65
    designs = [cfg.baseline, dict(cfg.baseline, suction_angle_deg=45.0)]
    weights = policy._prior_acquisition_weight(designs, completed)
    assert np.all(weights > 0.0)
    assert np.all(weights <= 1.0)
    sigma = policy._prior_sigma(np.vstack([cfg.encode(item) for item in designs]), completed)
    assert np.all(sigma > 0.0)


def test_c3x_geometry_gate_accepts_baseline_and_rejects_reversed_rows():
    cfg = load_optimization_config("configs/c3x_optimization_coarse.yaml")
    gate = C3XDownstreamGeometryGate()
    assert gate(cfg.baseline)
    invalid = dict(cfg.baseline, SS1_s=0.27, SS2_s=0.25)
    assert not gate(invalid)


def test_nasa_geometry_gate_rejects_coupled_position_angle_cavity_miss():
    cfg = load_optimization_config("configs/c3x_nasa_standard_mfbo.yaml")
    gate = build_geometry_gate("c3x_nasa44344")
    assert gate(cfg.baseline)
    invalid = dict(
        cfg.baseline,
        PS1_s=0.19658955571614206,
        PS2_s=0.2517801522705704,
        pressure_angle_deg=25.249675805680454,
    )
    assert not gate(invalid)


def test_demo_engine_runs_to_budget(tmp_path):
    cfg = replace(
        config(),
        database=tmp_path / "engine.sqlite3",
        run_root=tmp_path / "runs",
        budget=1.201,
        initial_designs=2,
        evaluator={"type": "demo", "demo_delay_seconds": 0.0},
    )
    engine = OptimizationEngine(cfg)
    engine.start()
    deadline = time.time() + 20.0
    while engine.state not in {EngineState.COMPLETED, EngineState.ERROR} and time.time() < deadline:
        time.sleep(0.05)
    assert engine.state == EngineState.COMPLETED
    completed = engine.store.trials(("completed",))
    assert [trial["fidelity"] for trial in completed] == ["L1", "L2", "L3"]
    assert abs(engine.store.cost_used() - 1.201) < 1e-12
