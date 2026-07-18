"""Review figure: single-airfoil external-flow domain with PERIODIC side walls.

Per review feedback:
  - one complete vane cut out of the flow (not two separated blades);
  - the two side walls are the same curved centreline translated by a fixed
    vector, so the periodic pair matches exactly without a large rectangular
    envelope;
  - the physical cascade pitch is kept as metadata separately.
Coolant cavities are intentionally omitted (to be built in SpaceClaim).
"""
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
from bofm.geometry.profile import densify_profile
from bofm.geometry.external_flow import build_airfoil_external_domain

root = Path(__file__).resolve().parents[1]
cfg = yaml.safe_load(open(root / "configs" / "c3x_baseline.yaml", encoding="utf-8"))
geom = cfg["geometry"]
pd = geom.get("passage_domain", {})

raw = P.clean_profile(P.load_profile(root / "configs" / "c3x_coordinates.csv"))
surfaces = P.build_surfaces(densify_profile(raw, n_per_surface=220, cluster=0.5))

dom = build_airfoil_external_domain(
    surfaces,
    pitch_mm=geom["pitch_mm"], axial_chord_mm=geom["axial_chord_mm"],
    up_chord=pd.get("upstream_axial_chords", 1.5),
    down_chord=pd.get("downstream_axial_chords", 1.0),
    inlet_angle_deg=0.0,
    exit_angle_deg=float(pd.get("downstream_periodic_angle_deg", -72.38)),
)

# periodic-pair check: upper must equal lower + the generated translation.
m = min(len(dom.side_lower_xy), len(dom.side_upper_xy))
periodic_err = float(np.max(np.linalg.norm(
    (dom.side_upper_xy[:m] - np.asarray(dom.periodic_translation_xy_mm)) - dom.side_lower_xy[:m],
    axis=1,
)))
y_widths = [
    float(abs(dom.inlet_xy[1, 1] - dom.inlet_xy[0, 1])),
    float(abs(dom.outlet_xy[1, 1] - dom.outlet_xy[0, 1])),
    float(dom.periodic_width_mm),
]
global_y_span = float(dom.outer_loop_xy[:, 1].max() - dom.outer_loop_xy[:, 1].min())

print("external flow domain (periodic side walls):")
print("  x_in/x_out      : %.1f / %.1f mm" % (dom.x_in, dom.x_out))
print("  physical pitch  : %.1f mm" % dom.physical_pitch_mm)
print("  periodic width  : %.1f mm" % dom.periodic_width_mm)
print("  global y span   : %.1f mm" % global_y_span)
print("  vane->wall gap  : %.1f mm (min, must be > 0)" % dom.min_wall_clearance_mm)
print("  inlet/outlet/periodic y widths: %.3f / %.3f / %.3f mm" % tuple(y_widths))
print("  periodic pair max mismatch |upper-translation-lower| : %.3g mm" % periodic_err)

# --- figure -------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 11))
ax.fill(dom.outer_loop_xy[:, 0], dom.outer_loop_xy[:, 1], color="tab:cyan",
        alpha=0.13, zorder=0, label="external flow fluid")
ax.plot(dom.side_lower_xy[:, 0], dom.side_lower_xy[:, 1], color="tab:orange",
        lw=1.8, label="periodic wall (lower)")
ax.plot(dom.side_upper_xy[:, 0], dom.side_upper_xy[:, 1], "--", color="tab:purple",
        lw=1.8, label="periodic wall (upper = lower + translation)")
ax.plot(dom.centerline_xy[:, 0], dom.centerline_xy[:, 1], ":", color="0.5",
        lw=1.0, label="centreline")
ax.plot(dom.inlet_xy[:, 0], dom.inlet_xy[:, 1], color="tab:green", lw=3, label="inlet")
ax.plot(dom.outlet_xy[:, 0], dom.outlet_xy[:, 1], color="tab:red", lw=3, label="outlet")
ax.text(dom.inlet_xy[0, 0] + 3.0, np.mean(dom.inlet_xy[:, 1]),
        "W=%.1f mm" % y_widths[0], color="tab:green", fontsize=8, va="center")
ax.text(dom.outlet_xy[0, 0] - 28.0, np.mean(dom.outlet_xy[:, 1]),
        "W=%.1f mm" % y_widths[1], color="tab:red", fontsize=8, va="center")
ax.fill(dom.airfoil_xy[:, 0], dom.airfoil_xy[:, 1], facecolor="0.82",
        edgecolor="k", lw=1.4, zorder=3, label="vane (cut out)")

ax.set_aspect("equal"); ax.grid(True, alpha=0.3); ax.legend(loc="upper right", fontsize=8)
ax.set_xlabel("x [mm] (axial)"); ax.set_ylabel("y [mm] (tangential)")
ax.set_title("C3X single-airfoil external flow (periodic walls) — review")
out_png = root / "configs" / "c3x_external_flow.png"
ax.set_title("C3X single-airfoil external flow (curved translated periodics)")
fig.savefig(out_png, dpi=120, bbox_inches="tight"); print("saved:", out_png)

ax.set_xlim(-20, 90); ax.set_ylim(-10, 145)
ax.set_title("C3X vane in external flow (LE zoom) — review")
ax.set_title("C3X vane in external flow (LE zoom)")
fig.savefig(root / "configs" / "c3x_external_flow_zoom.png", dpi=130, bbox_inches="tight")
print("saved:", root / "configs" / "c3x_external_flow_zoom.png")

json.dump({
    "units": "mm",
    "topology": "single airfoil cut out; curved duct with translated periodic side walls",
    "physical_pitch_mm": dom.physical_pitch_mm,
    "pitch_mm": dom.periodic_width_mm,
    "periodic_width_mm": dom.periodic_width_mm,
    "periodic_translation_xy_mm": list(dom.periodic_translation_xy_mm),
    "y_low": dom.y_low, "y_high": dom.y_high,
    "x_in": dom.x_in, "x_out": dom.x_out,
    "min_wall_clearance_mm": dom.min_wall_clearance_mm,
    "periodic_pair_max_mismatch_mm": periodic_err,
    "periodic_width_check_mm": {
        "inlet": y_widths[0],
        "outlet": y_widths[1],
        "periodic_translation": y_widths[2],
    },
    "global_y_span_mm": global_y_span,
    "outer_loop_xy_mm": dom.outer_loop_xy.tolist(),
    "airfoil_xy_mm": dom.airfoil_xy.tolist(),
    "periodic_lower_xy_mm": dom.side_lower_xy.tolist(),
    "periodic_upper_xy_mm": dom.side_upper_xy.tolist(),
    "inlet_xy_mm": dom.inlet_xy.tolist(), "outlet_xy_mm": dom.outlet_xy.tolist(),
}, open(root / "configs" / "c3x_external_flow.json", "w", encoding="utf-8"), indent=2)
print("wrote:", root / "configs" / "c3x_external_flow.json")
