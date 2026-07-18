from __future__ import annotations

import pytest

from scripts.compare_nasa_snr import binned_rows, pair_face_rows


def _row(x: float, q: float) -> dict[str, str]:
    return {
        "side": "pressure",
        "surface_distance_pct": str(x * 100.0),
        "x_m": str(x),
        "y_m": "0.0",
        "z_m": "0.0",
        "face_area_m2": "1.0",
        "heat_flux": str(q),
    }


def test_paired_heat_flux_gives_stanton_number_reduction() -> None:
    fc = [_row(0.2, 60.0), _row(0.4, 80.0)]
    nfc = [_row(0.2, 100.0), _row(0.4, 100.0)]

    paired = pair_face_rows(
        fc, nfc, "heat_flux", tolerance_m=1e-12
    )

    assert [row["snr"] for row in paired] == pytest.approx([0.4, 0.2])
    binned = binned_rows(paired, bin_width_pct=25.0)
    assert [row["snr"] for row in binned] == pytest.approx([0.4, 0.2])
