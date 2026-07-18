from __future__ import annotations

from copy import deepcopy

import pytest

from bofm.workbench.bc import load_simulation_case, workbench_inlet_bc


def test_nasa_44344_uses_measured_slice_mass_flows() -> None:
    case = load_simulation_case("nasa_44344_validation")
    bcs = workbench_inlet_bc(case)

    assert bcs["qian"]["type"] == "mass-flow-inlet"
    assert bcs["qian"]["mass_flow_rate_kg_s"] == pytest.approx(0.0012433465)
    assert bcs["ss"]["mass_flow_rate_kg_s"] == pytest.approx(0.0026114173)
    assert bcs["ps"]["mass_flow_rate_kg_s"] == pytest.approx(0.0014655118)
    assert bcs["ps"]["gauge_total_pressure_Pa"] == pytest.approx(299386.5)


def test_pressure_ratio_remains_default_coolant_boundary_mode() -> None:
    case = deepcopy(load_simulation_case("nasa_44344_validation"))
    case.pop("coolant_boundary")
    bcs = workbench_inlet_bc(case)

    assert bcs["qian"]["type"] == "pressure-inlet"
    assert "mass_flow_rate_kg_s" not in bcs["qian"]


def test_measured_mass_flow_requires_configured_value() -> None:
    case = deepcopy(load_simulation_case("nasa_44344_validation"))
    del case["coolant"]["pressure"]["periodic_14p85mm_mass_flow_kg_s"]

    with pytest.raises(KeyError, match="pressure"):
        workbench_inlet_bc(case)


def test_nasa_snr_nfc_uses_zero_net_coolant_flow() -> None:
    case = load_simulation_case("nasa_44344_snr_nfc")
    bcs = workbench_inlet_bc(case)

    for zone in ("qian", "ss", "ps"):
        assert bcs[zone]["type"] == "mass-flow-inlet"
        assert bcs[zone]["mass_flow_rate_kg_s"] == 0.0
        assert bcs[zone]["mass_flow_source_key"] == "zero_mass_flow"
