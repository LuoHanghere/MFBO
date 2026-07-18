from pathlib import Path

from scripts.export_workbench_film_results import parse_convergence_log


def test_parse_convergence_log_temperature_limits(tmp_path: Path) -> None:
    log = tmp_path / "fluent.trn"
    log.write_text(
        """
 temperature limited to 3.000000e+02 in 7 cells on zone 339 in domain 1
 temperature limited to 1.000000e+03 in 120 cells on zone 339 in domain 1
 temperature limited to 1.000000e+03 in 115 cells on zone 339 in domain 1
  2000  1.2463e-03  3.9113e-06  8.1032e-06  3.1822e-06  6.9711e-05  1.1058e-04  9.2893e-04
""",
        encoding="utf-8",
    )

    parsed = parse_convergence_log(log)

    assert parsed["warnings"]["temperature_limited"] == 3
    assert parsed["last_residual_row"]["iteration"] == 2000
    assert parsed["temperature_limits"]["last_event"] == {
        "limit_K": 1000.0,
        "cell_count": 115,
        "zone_id": 339,
    }
    by_limit = {row["limit_K"]: row for row in parsed["temperature_limits"]["by_limit"]}
    assert by_limit[300.0]["max_cell_count"] == 7
    assert by_limit[1000.0]["event_count"] == 2
    assert by_limit[1000.0]["max_cell_count"] == 120
