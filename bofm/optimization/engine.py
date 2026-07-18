"""Threaded, resumable optimization state machine."""
from __future__ import annotations

import threading
import traceback
from enum import Enum
from pathlib import Path
from typing import Callable

from .config import OptimizationConfig
from .evaluator import build_evaluator
from .storage import ExperimentStore
from .surrogate import PhysicsInformedPolicy


class EngineState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


class OptimizationEngine:
    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.store = ExperimentStore(config.database)
        recovered = self.store.recover_interrupted()
        self.store.set_metadata("experiment_name", config.name)
        self.store.set_metadata("budget", config.budget)
        if recovered:
            self.store.add_event(f"marked {recovered} interrupted trial(s) as failed", level="warning")
        self.policy = PhysicsInformedPolicy(config)
        self.evaluator = build_evaluator(config)
        self.state = EngineState.IDLE
        self.current_trial_id: int | None = None
        self._condition = threading.Condition()
        self._stop_requested = False
        self._thread: threading.Thread | None = None
        self._callbacks: list[Callable[[], None]] = []

    def subscribe(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def start(self) -> None:
        with self._condition:
            if self._thread and self._thread.is_alive():
                if self.state == EngineState.PAUSED:
                    self.state = EngineState.RUNNING
                    self.store.add_event("optimization resumed")
                    self._condition.notify_all()
                    self._notify()
                return
            self._stop_requested = False
            self.state = EngineState.RUNNING
            self.store.add_event("optimization started")
            self._thread = threading.Thread(target=self._run, daemon=True, name="bofm-optimizer")
            self._thread.start()
            self._notify()

    def pause(self) -> None:
        with self._condition:
            if self.state == EngineState.RUNNING:
                self.state = EngineState.PAUSED
                detail = " after current trial" if self.current_trial_id else ""
                self.store.add_event(f"pause requested{detail}")
                self._notify()

    def stop(self) -> None:
        with self._condition:
            self._stop_requested = True
            self.state = EngineState.STOPPING
            self.store.add_event("stop requested; current external stage is allowed to finish")
            self._condition.notify_all()
            self._notify()

    def snapshot(self) -> dict:
        trials = self.store.trials()
        completed = [item for item in trials if item["status"] == "completed"]
        feasible = [
            item for item in completed
            if all(
                float(item["constraints"].get(spec.name, float("inf"))) <= spec.upper
                for spec in self.config.constraints
            )
        ]
        target_name = self.config.fidelities[-1].name
        target_feasible = [item for item in feasible if item["fidelity"] == target_name]
        if target_feasible:
            feasible = target_feasible
        if feasible:
            key = lambda item: float(item["objective"])
            best = (max if self.config.maximize else min)(feasible, key=key)
        else:
            best = None
        return {
            "state": self.state.value,
            "current_trial_id": self.current_trial_id,
            "budget": self.config.budget,
            "cost_used": self.store.cost_used(),
            "trials": trials,
            "best": best,
            "events": self.store.events(100),
        }

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    while self.state == EngineState.PAUSED and not self._stop_requested:
                        self._condition.wait(timeout=0.5)
                    if self._stop_requested:
                        self.state = EngineState.IDLE
                        break
                recent = self.store.trials()[-3:]
                if len(recent) == 3 and all(item["status"] == "failed" for item in recent):
                    self.state = EngineState.ERROR
                    self.store.add_event(
                        "circuit breaker opened after three consecutive failures; "
                        "inspect the shared geometry, solver, or license cause before resuming",
                        level="error",
                    )
                    break
                if self.store.cost_used() >= self.config.budget:
                    self.state = EngineState.COMPLETED
                    self.store.add_event("equivalent high-fidelity budget reached")
                    break
                proposal = self.policy.propose(self.store.trials())
                fidelity = self.config.fidelity(proposal.fidelity)
                if self.store.cost_used() + fidelity.relative_cost > self.config.budget + 1e-12:
                    self.state = EngineState.COMPLETED
                    self.store.add_event("remaining budget is below the cheapest admissible proposal")
                    break
                trial_id = self.store.create_trial(
                    proposal.design,
                    proposal.fidelity,
                    proposal.source,
                    fidelity.relative_cost,
                    proposal.predicted,
                )
                run_dir = self.config.run_root / f"trial_{trial_id:04d}_{proposal.fidelity}"
                self.current_trial_id = trial_id
                self.store.mark_running(trial_id, run_dir)
                self.store.add_event(
                    f"trial {trial_id} started ({proposal.source}, {proposal.fidelity})",
                    trial_id=trial_id,
                )
                self._notify()
                try:
                    result = self.evaluator.evaluate(
                        proposal.design,
                        proposal.fidelity,
                        run_dir,
                        lambda message: self.store.add_event(message, trial_id=trial_id),
                    )
                    self.store.complete(
                        trial_id, result.objective, result.constraints, result.metrics
                    )
                    self.store.add_event(
                        f"trial {trial_id} completed: {self.config.objective_name}={result.objective:.6f}",
                        trial_id=trial_id,
                    )
                except Exception as exc:
                    self.store.fail(trial_id, traceback.format_exc())
                    self.store.add_event(f"trial {trial_id} failed: {exc}", level="error", trial_id=trial_id)
                finally:
                    self.current_trial_id = None
                    self._notify()
        except Exception as exc:
            self.state = EngineState.ERROR
            self.store.add_event(f"optimizer error: {exc}", level="error")
        finally:
            self.current_trial_id = None
            self._notify()

    def _notify(self) -> None:
        for callback in tuple(self._callbacks):
            try:
                callback()
            except Exception:
                pass
