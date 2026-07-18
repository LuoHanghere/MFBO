"""Digitize the Kumar case-1 forward-injection effectiveness curves.

The source plots are raster figures, so the retained CSVs include an explicit
digitization uncertainty and the JSON sidecar records the pixel calibration.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import fitz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "978-981-19-3379-0_28-39.pdf"
OUT = ROOT / "configs" / "validation"
TMP = ROOT / "tmp" / "pdfs" / "kumar_eta_digitization"

# Values visually digitized from the forward-hole open-circle curve after a
# calibrated 3x rendering.  The 0.5-D sampling is finer than the CFD comparison
# requirement and avoids claiming false precision from the raster source.
Z = np.arange(-7.5, 7.5001, 0.5)
PS_ETA = np.array([
    0.395, 0.414, 0.439, 0.451, 0.461, 0.459, 0.461, 0.480,
    0.520, 0.498, 0.438, 0.419, 0.408, 0.419, 0.459, 0.512,
    0.526, 0.498, 0.488, 0.493, 0.510, 0.492, 0.436, 0.400,
    0.401, 0.405, 0.429, 0.451, 0.447, 0.426, 0.405,
])
SS_ETA = np.array([
    0.155, 0.220, 0.352, 0.495, 0.398, 0.210, 0.161, 0.275,
    0.410, 0.539, 0.410, 0.174, 0.125, 0.225, 0.407, 0.513,
    0.439, 0.213, 0.157, 0.259, 0.407, 0.521, 0.434, 0.251,
    0.125, 0.231, 0.416, 0.531, 0.398, 0.315, 0.170,
])

CALIBRATION = {
    "render_zoom": 3.0,
    "pressure": {
        "pdf_page": 8,
        "crop_box_px": [170, 130, 650, 500],
        "axis_origin_in_crop_px": [272, 352],
        "pixels_per_Z_over_D": 28.0,
        "pixels_per_eta": 304.0,
        "station_X_over_Cax": 0.31,
        "alpha_deg": 30.0,
    },
    "suction": {
        "pdf_page": 9,
        "crop_box_px": [150, 130, 650, 510],
        "axis_origin_in_crop_px": [284, 354],
        "pixels_per_Z_over_D": 28.0,
        "pixels_per_eta": 305.0,
        "station_X_over_Cax": 0.48,
        "alpha_deg": 35.0,
    },
}


def write_curve(path: Path, side: str, station: float, eta: np.ndarray) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "side", "orientation", "alpha_deg", "X_over_Cax", "Z_over_D",
            "eta", "eta_digitization_uncertainty", "Z_over_D_uncertainty",
        ])
        writer.writeheader()
        alpha = 30.0 if side == "pressure" else 35.0
        for z, value in zip(Z, eta):
            writer.writerow({
                "side": side,
                "orientation": "forward",
                "alpha_deg": alpha,
                "X_over_Cax": station,
                "Z_over_D": f"{z:.3f}",
                "eta": f"{value:.4f}",
                "eta_digitization_uncertainty": "0.015",
                "Z_over_D_uncertainty": "0.10",
            })


def render_pages() -> dict[str, Image.Image]:
    TMP.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF)
    out = {}
    for side, page_index in (("pressure", 7), ("suction", 8)):
        page_path = TMP / f"page-{page_index + 1:02d}.png"
        doc[page_index].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).save(page_path)
        image = Image.open(page_path)
        out[side] = image.crop(tuple(CALIBRATION[side]["crop_box_px"]))
    return out


def add_overlay(ax, image: Image.Image, side: str, eta: np.ndarray) -> None:
    cal = CALIBRATION[side]
    x0, y0 = cal["axis_origin_in_crop_px"]
    x = x0 + cal["pixels_per_Z_over_D"] * Z
    y = y0 - cal["pixels_per_eta"] * eta
    ax.imshow(image)
    ax.plot(x, y, "r.-", ms=4, lw=0.8, label="retained digitization")
    ax.set_axis_off()
    ax.set_title(f"{side}: visual calibration check")
    ax.legend(loc="lower left", fontsize=7)


def main() -> int:
    if not PDF.exists():
        raise FileNotFoundError(PDF)
    if len(Z) != len(PS_ETA) or len(Z) != len(SS_ETA):
        raise RuntimeError("Digitized point count mismatch")
    OUT.mkdir(parents=True, exist_ok=True)
    ps_path = OUT / "kumar_fig6_ps_forward_30deg.csv"
    ss_path = OUT / "kumar_fig7_ss_forward_35deg.csv"
    write_curve(ps_path, "pressure", 0.31, PS_ETA)
    write_curve(ss_path, "suction", 0.48, SS_ETA)

    metadata = {
        "source": {
            "paper": "Kumar et al., A Numerical Study of Film Cooling on NASA-C3X Vane by Forward and Reverse Injection",
            "file": PDF.name,
            "figures": [6, 7],
        },
        "case": {
            "orientation": "forward",
            "pressure_angle_deg": 30.0,
            "suction_angle_deg": 35.0,
            "pressure_ratio": 1.15,
            "temperature_ratio": 3.0,
        },
        "method": "calibrated raster-plot digitization with visual overlay QA",
        "uncertainty": {
            "eta_absolute": 0.015,
            "Z_over_D": 0.10,
            "note": "Do not use these raster-derived values to claim agreement below the stated uncertainty.",
        },
        "calibration": CALIBRATION,
        "outputs": [ps_path.name, ss_path.name],
    }
    (OUT / "kumar_case1_digitization.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    images = render_pages()
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5))
    add_overlay(axes[0, 0], images["pressure"], "pressure", PS_ETA)
    add_overlay(axes[1, 0], images["suction"], "suction", SS_ETA)
    axes[0, 1].plot(Z, PS_ETA, "ko-", ms=3)
    axes[0, 1].set(title="Kumar Fig. 6 retained forward curve", ylabel="eta", xlim=(-7.5, 7.5), ylim=(0, 1))
    axes[1, 1].plot(Z, SS_ETA, "ko-", ms=3)
    axes[1, 1].set(title="Kumar Fig. 7 retained forward curve", xlabel="Z/D", ylabel="eta", xlim=(-7.5, 7.5), ylim=(0, 1))
    for ax in axes[:, 1]:
        ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "kumar_case1_digitization_overlay.png", dpi=180)
    plt.close(fig)
    print(ps_path)
    print(ss_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
