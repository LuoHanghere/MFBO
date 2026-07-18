from __future__ import annotations

import pytest

from bofm.cfd.nofilm import SINGH_AIR_POLYNOMIALS, singh_air_properties
from bofm.cfd.workbench_setup import set_solution_limits, set_under_relaxation_factors


class _State:
    def __init__(self, state):
        self.state = dict(state)

    def get_state(self):
        return dict(self.state)

    def set_state(self, state):
        self.state = dict(state)


class _Solver:
    def __init__(self):
        controls = type("Controls", (), {})()
        controls.under_relaxation = _State({"mom": 0.7, "temperature": 1.0})
        controls.limits = _State({
            "min_temperature": 1.0,
            "max_temperature": 5000.0,
            "max_turb_visc_ratio": 1.0e5,
        })
        solution = type("Solution", (), {"controls": controls})()
        self.settings = type("Settings", (), {"solution": solution})()


@pytest.mark.parametrize("temperature_K", [100.0, 591.0, 773.0, 1773.0, 2300.0])
def test_singh_air_properties_are_physical(temperature_K):
    values = singh_air_properties(temperature_K)
    assert 900.0 < values["specific_heat"] < 1400.0
    assert 0.005 < values["thermal_conductivity"] < 0.2
    assert 5.0e-6 < values["viscosity"] < 2.0e-4


def test_singh_coefficients_are_stored_in_fluent_order():
    assert SINGH_AIR_POLYNOMIALS["specific_heat"][0] == 1050.0
    assert SINGH_AIR_POLYNOMIALS["viscosity"][-1] == 1.70e-14


def test_singh_fit_rejects_extrapolation():
    with pytest.raises(ValueError, match="100 to 2300 K"):
        singh_air_properties(99.0)


def test_fluent_242_control_aliases_are_applied():
    solver = _Solver()
    urfs = set_under_relaxation_factors(
        solver, {"momentum": 0.5, "energy": 0.3}
    )
    limits = set_solution_limits(
        solver, {"temperature_min": 100.0, "temperature_max": 2300.0}
    )
    assert urfs == {"mom": 0.5, "temperature": 0.3}
    assert limits == {"min_temperature": 100.0, "max_temperature": 2300.0}
    assert solver.settings.solution.controls.under_relaxation.state["mom"] == 0.5
