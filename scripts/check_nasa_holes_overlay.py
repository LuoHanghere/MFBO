"""Review plot for NASA CR-182133 Fig. 8 film-row locations.

The raw Fig. 8 U/V anchors need a frame fit before they can be shown on our
cascade x/y section. That fit is useful as a reference, but it is not accurate
enough to use those transformed points as hole exits. This plot therefore shows
two layers:

  - faint hollow circles: raw Fig. 8 U/V anchors after the global fit
  - solid markers: surface-projected / CAD-ready row exits used by our model
"""
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
from bofm.geometry.film_holes import (
    NASA_FILM_HOLES_UV_CM,
    NASA_RADIAL_HOLES_UV_CM,
    fit_vane_to_cascade,
)
from bofm.geometry.profile import densify_profile


root = Path(__file__).resolve().parents[1]
cfg = yaml.safe_load((root / "configs" / "c3x_baseline.yaml").read_text(encoding="utf-8"))
raw = P.clean_profile(P.load_profile(root / "configs" / "c3x_coordinates.csv"))
dense = densify_profile(raw, n_per_surface=220, cluster=0.5)
surfaces = P.build_surfaces(dense)
profile = np.asarray(dense)
cav = json.load(open(root / "configs" / "c3x_cavities.json", encoding="utf-8"))["cavities"]

fit = fit_vane_to_cascade(surfaces)
T = fit["transform"]
print("chord-aligned transform: rot=%.1f deg refl=%g RMS(radial->camber)=%.2f mm"
      % (fit["angle_deg"], fit["reflection"], fit["rms_camber_mm"]))


def nearest_surface_arc_mm(point_xy, surface_xy):
    surface_xy = np.asarray(surface_xy, dtype=float)
    seg = np.linalg.norm(np.diff(surface_xy, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    i = int(np.argmin(np.linalg.norm(surface_xy - point_xy, axis=1)))
    return float(arc[i]), float(np.linalg.norm(surface_xy[i] - point_xy)), surface_xy[i]


def raw_uv_record(hid, group):
    uv = np.asarray(NASA_FILM_HOLES_UV_CM[hid], dtype=float)
    xy = np.asarray(T(uv), dtype=float)
    ss_arc, ss_dist, ss_pt = nearest_surface_arc_mm(xy, surfaces["suction"].xy)
    ps_arc, ps_dist, ps_pt = nearest_surface_arc_mm(xy, surfaces["pressure"].xy)
    if group == "suction":
        surface = "suction"
        arc = ss_arc
        projected = ss_pt
    elif group == "pressure":
        surface = "pressure"
        arc = -ps_arc
        projected = ps_pt
    else:
        if ss_dist <= ps_dist:
            surface = "suction"
            arc = ss_arc
            projected = ss_pt
        else:
            surface = "pressure"
            arc = -ps_arc
            projected = ps_pt
    return {
        "nasa_hole": hid,
        "group": group,
        "uv_cm": [float(uv[0]), float(uv[1])],
        "raw_fit_xy_mm": [float(xy[0]), float(xy[1])],
        "projected_surface_xy_mm": [float(projected[0]), float(projected[1])],
        "nearest_surface": surface,
        "signed_arc_from_le_mm": float(arc),
        "distance_to_suction_mm": float(ss_dist),
        "distance_to_pressure_mm": float(ps_dist),
    }


raw_rows = []
for group_name, ids in [
    ("suction", [11, 12]),
    ("leading_edge", [13, 14, 15, 16, 17]),
    ("pressure", [18, 19]),
]:
    raw_rows.extend(raw_uv_record(hid, group_name) for hid in ids)

# CAD-ready surface exits: LE from the corrected showerhead layout; body rows
# from the baseline parametrization already consumed by CAD/mesh builders.
showerhead_path = root / "configs" / "c3x_showerhead_layout.json"
showerhead = json.loads(showerhead_path.read_text(encoding="utf-8"))["holes"]
body_holes = P.place_holes(cfg, surfaces)

body_nasa_by_row = {"SS1": 12, "SS2": 11, "PS1": 18, "PS2": 19}
surface_rows = []
for h in body_holes:
    surface_rows.append({
        "id": h.row_id,
        "nasa_hole": body_nasa_by_row.get(h.row_id),
        "group": h.surface,
        "surface_xy_mm": [float(h.x_mm), float(h.y_mm)],
        "s_over_surface": float(h.s_frac),
        "tangent_deg": float(h.tangent_deg),
        "injection_deg": float(h.injection_deg),
    })
for h in showerhead:
    surface_rows.append({
        "id": h["id"],
        "nasa_hole": h.get("nasa_hole"),
        "group": "leading_edge",
        "surface_xy_mm": [float(h["surface_point_mm"][0]), float(h["surface_point_mm"][1])],
        "arc_s_mm": float(h["arc_s_mm"]),
        "slant_deg": float(h["slant_deg"]),
        "skew_deg": float(h["skew_deg"]),
    })

out_rows = root / "configs" / "c3x_nasa_film_rows_marked.json"
out_rows.write_text(json.dumps({
    "source": "NASA CR-182133 Fig. 8 plus CAD-ready surface row exits",
    "units": "uv in cm; xy and arc in mm",
    "fit": {k: v for k, v in fit.items() if k != "transform"},
    "raw_fig8_uv_rows": raw_rows,
    "surface_rows": surface_rows,
}, indent=2), encoding="utf-8")
print("saved:", out_rows.relative_to(root))

rad = np.array([T(NASA_RADIAL_HOLES_UV_CM[k]) for k in range(1, 11)])

fig, ax = plt.subplots(figsize=(10, 11))
ax.fill(profile[:, 0], profile[:, 1], facecolor="0.86", edgecolor="k", lw=1.3, zorder=2)
col = {"LE_plenum": "tab:purple", "SS_plenum": "tab:cyan", "PS_plenum": "tab:olive"}
for c in cav:
    poly = np.vstack([c["profile_xy_mm"], c["profile_xy_mm"][0]])
    ax.fill(poly[:, 0], poly[:, 1], color=col.get(c.get("role"), "0.6"), alpha=0.35,
            zorder=3, label=c.get("role"))

ax.plot(rad[:, 0], rad[:, 1], "x", color="0.25", ms=8, mew=1.6, zorder=5,
        label="radial holes 1-10 (raw fit)")

raw_colors = {"leading_edge": "tab:red", "suction": "tab:blue", "pressure": "tab:green"}
for r in raw_rows:
    x, y = r["raw_fit_xy_mm"]
    ax.plot(x, y, "o", mfc="none", mec=raw_colors[r["group"]], mew=1.2,
            ms=8, alpha=0.35, zorder=6)

for h in showerhead:
    x, y, _ = h["surface_point_mm"]
    ax.plot(x, y, "o", color="tab:red", ms=7, zorder=8)
    cyl = h["cylinder_mm"]
    s0 = np.asarray(cyl["start_mm"])
    e0 = np.asarray(cyl["end_mm"])
    ax.plot([s0[0], e0[0]], [s0[1], e0[1]], color="tab:red", lw=1.8, zorder=7)
    ax.annotate("R%d" % h["row"], (x, y), xytext=(-26, 0), textcoords="offset points",
                fontsize=9, color="tab:red", va="center", zorder=9)

for h in body_holes:
    color = "tab:blue" if h.surface == "suction" else "tab:green"
    nasa = body_nasa_by_row[h.row_id]
    ax.plot(h.x_mm, h.y_mm, "o", color=color, ms=8, zorder=8)
    ax.annotate("%s/%d" % (h.row_id, nasa), (h.x_mm, h.y_mm),
                xytext=(6, 5), textcoords="offset points", fontsize=9,
                color=color, weight="bold", zorder=9)

ax.plot([], [], "o", color="tab:red", label="LE rows on surface")
ax.plot([], [], "o", color="tab:blue", label="suction rows on surface")
ax.plot([], [], "o", color="tab:green", label="pressure rows on surface")
ax.plot([], [], "o", mfc="none", mec="0.45", alpha=0.45, label="raw Fig. 8 U/V fit")

ax.set_aspect("equal")
ax.grid(True, alpha=0.3)
ax.legend(loc="lower right", fontsize=9)
ax.set_xlabel("x [mm] (axial)")
ax.set_ylabel("y [mm] (tangential)")
ax.set_title("C3X film rows on blade surface - raw Fig. 8 anchors shown hollow")
ax.set_xlim(-12, 85)
ax.set_ylim(-8, 138)
fig.savefig(root / "configs" / "c3x_nasa_holes_overlay.png", dpi=130, bbox_inches="tight")
print("saved: configs/c3x_nasa_holes_overlay.png")

ax.set_xlim(-12, 42)
ax.set_ylim(88, 134)
fig.savefig(root / "configs" / "c3x_nasa_holes_overlay_LE.png", dpi=140, bbox_inches="tight")
print("saved: configs/c3x_nasa_holes_overlay_LE.png")
