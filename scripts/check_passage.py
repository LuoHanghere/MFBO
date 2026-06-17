"""Plot the single-pitch periodic passage so the domain can be approved before
scripting it in SpaceClaim."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from bofm.geometry import parametrization as P
from bofm.geometry.passage import build_passage

root = Path(__file__).resolve().parents[1]
config = yaml.safe_load(open(root / "configs" / "c3x_baseline.yaml", encoding="utf-8"))
geom = config["geometry"]
profile = P.load_profile(root / "configs" / "c3x_coordinates.csv")
surfaces = P.build_surfaces(profile)

pas = build_passage(surfaces,
                    pitch_mm=geom["pitch_mm"],
                    axial_chord_mm=geom["axial_chord_mm"],
                    up_chord=geom.get("passage_domain", {}).get("upstream_axial_chords", 1.0),
                    down_chord=geom.get("passage_domain", {}).get("downstream_axial_chords", 1.5),
                    inlet_angle_deg=0.0,
                    exit_angle_deg=geom["air_exit_angle_deg"])

print("pitch          : %.2f mm" % pas.pitch_mm)
print("x_in / x_out   : %.1f / %.1f mm" % (pas.x_in, pas.x_out))
print("loop points    : %d" % len(pas.loop_xy))

# export the passage loop for the SpaceClaim journal
passage_json = root / "configs" / "c3x_passage.json"
json.dump({
    "case": config["case"]["name"],
    "units": "mm",
    "span_mm": geom["span_mm"],
    "pitch_mm": pas.pitch_mm,
    "x_in": pas.x_in, "x_out": pas.x_out,
    "loop_xy_mm": [[float(x), float(y)] for x, y in pas.loop_xy],
}, open(passage_json, "w", encoding="utf-8"), indent=2)
print("wrote:", passage_json)

fig, ax = plt.subplots(figsize=(9, 9))
# filled passage
ax.fill(pas.loop_xy[:, 0], pas.loop_xy[:, 1], color="tab:cyan", alpha=0.18, zorder=0)

# both blades (solid)
pitch = np.array([0.0, pas.pitch_mm])
ax.fill(profile[:, 0], profile[:, 1], color="0.5", zorder=3)
ax.fill(profile[:, 0], profile[:, 1] + pas.pitch_mm, color="0.7", zorder=3)

# colour the boundary segments
colours = {
    "inlet": ("tab:green", "inlet"),
    "outlet": ("tab:red", "outlet"),
    "wall_blade0_suction": ("k", "wall (blade0 suction)"),
    "wall_blade1_pressure": ("k", None),
    "periodic_up_lower": ("tab:orange", "periodic"),
    "periodic_up_upper": ("tab:orange", None),
    "periodic_down_lower": ("tab:orange", None),
    "periodic_down_upper": ("tab:orange", None),
}
for name, seg in pas.segments.items():
    c, lab = colours[name]
    ax.plot(seg[:, 0], seg[:, 1], c, lw=2.2, label=lab, zorder=4)

ax.set_aspect("equal")
ax.grid(True, alpha=0.3)
ax.legend(loc="upper left")
ax.set_xlabel("x [mm] (axial)")
ax.set_ylabel("y [mm] (tangential)")
ax.set_title("C3X single-pitch periodic passage (no-film validation domain)")
out = root / "configs" / "c3x_passage.png"
fig.savefig(out, dpi=120, bbox_inches="tight")
print("saved:", out)
