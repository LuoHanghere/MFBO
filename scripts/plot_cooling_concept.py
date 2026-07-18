"""Plot film-cooled fluid topology: passage + box plenums + cylindrical holes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from bofm.geometry import parametrization as P
from bofm.geometry.passage import build_passage
from bofm.geometry.profile import densify_profile
from scripts.build_film_layout import build_layout


def build_concept(config: dict, *, mode: str = "unit-cell",
                  unit_span_mm: float | None = 20.0) -> dict:
    root = Path(__file__).resolve().parents[1]
    raw = P.load_profile(root / config["geometry"]["airfoil_coordinates"])
    dense = densify_profile(raw)
    passage_cfg = config["geometry"].get("passage_domain", {})
    exit_deg = passage_cfg.get("downstream_periodic_angle_deg")
    if exit_deg is None:
        exit_deg = -abs(float(config["geometry"]["air_exit_angle_deg"]))
    passage = build_passage(
        P.build_surfaces(dense),
        pitch_mm=float(config["geometry"]["pitch_mm"]),
        axial_chord_mm=float(config["geometry"]["axial_chord_mm"]),
        up_chord=float(passage_cfg.get("upstream_axial_chords", 1.0)),
        down_chord=float(passage_cfg.get("downstream_axial_chords", 1.0)),
        exit_angle_deg=float(exit_deg),
    )
    layout = build_layout(config, design=None, mode=mode, unit_span_mm=unit_span_mm)
    return {
        "mode": mode,
        "inspection_span_mm": unit_span_mm,
        "passage_loop_xy_mm": passage.loop_xy.tolist(),
        "profile_xy_mm": dense.tolist(),
        "pitch_mm": float(config["geometry"]["pitch_mm"]),
        "layout": layout,
    }


def plot_concept(concept: dict, out_png: Path) -> None:
    profile = np.asarray(concept["profile_xy_mm"], dtype=float)
    pitch = float(concept["pitch_mm"])
    passage = np.asarray(concept["passage_loop_xy_mm"], dtype=float)
    layout = concept["layout"]
    colors = {"suction": "tab:red", "pressure": "tab:blue"}

    fig, ax = plt.subplots(figsize=(8, 10))
    ax.plot(passage[:, 0], passage[:, 1], color="tab:cyan", alpha=0.45, lw=1.2,
            label="mainstream passage")
    ax.fill(profile[:, 0], profile[:, 1], color="0.86", edgecolor="0.35", lw=1.0)
    upper = profile + np.array([0.0, pitch])
    ax.fill(upper[:, 0], upper[:, 1], color="0.92", edgecolor="0.55", lw=1.0)

    for plenum in layout.get("plenums", []):
        lo = plenum["min_corner_mm"]
        hi = plenum["max_corner_mm"]
        xs = [lo[0], hi[0], hi[0], lo[0], lo[0]]
        ys = [lo[1], lo[1], hi[1], hi[1], lo[1]]
        color = colors[plenum["surface"]]
        ax.fill(xs, ys, color=color, alpha=0.20)
        ax.plot(xs, ys, "--", color=color, lw=1.5)
        ax.text(0.5 * (lo[0] + hi[0]), 0.5 * (lo[1] + hi[1]), plenum["id"],
                color=color, fontsize=9, ha="center", va="center")

    for inst in layout.get("instances", []):
        cyl = inst["cylinder_mm"]
        s = np.asarray(cyl["start_mm"][:2], dtype=float)
        e = np.asarray(cyl["end_mm"][:2], dtype=float)
        color = colors[inst["surface"]]
        ax.plot([s[0], e[0]], [s[1], e[1]], color=color, lw=2.0)
        ax.plot(s[0], s[1], "o", color=color, ms=4)
        ax.text(s[0] + 0.6, s[1] + 0.6, inst["id"], color=color, fontsize=7)

    ax.set_aspect("equal")
    ax.grid(True, alpha=0.25)
    ax.set_xlabel("x [mm] axial")
    ax.set_ylabel("y [mm] tangential")
    ax.set_title("Film fluid topology: passage + box plenum + cylindrical holes")
    ax.legend(loc="lower left")
    fig.savefig(out_png, dpi=150, bbox_inches="tight")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(root / "configs" / "c3x_baseline.yaml"))
    ap.add_argument("--mode", choices=["unit-cell", "full-span"], default="unit-cell")
    ap.add_argument("--unit-span-mm", type=float, default=20.0)
    ap.add_argument("--out-json", default=str(root / "configs" / "c3x_cooling_concept.json"))
    ap.add_argument("--out-png", default=str(root / "configs" / "c3x_cooling_concept.png"))
    args = ap.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    concept = build_concept(config, mode=args.mode, unit_span_mm=args.unit_span_mm)
    Path(args.out_json).write_text(json.dumps(concept, indent=2), encoding="utf-8")
    plot_concept(concept, Path(args.out_png))
    topo_ok = concept["layout"].get("topology", {}).get("ok", False)
    print("topology ok:", topo_ok)
    print("wrote:", args.out_json)
    print("wrote:", args.out_png)
    return 0 if topo_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
