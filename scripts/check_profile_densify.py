"""Verify the densified vane contour: arc lengths + before/after TE smoothness plot.

Splines the suction/pressure surfaces separately and resamples with end-clustering
(see bofm.geometry.profile.densify_profile), then:
  * reports raw vs densified surface arc lengths (must stay near NASA Table III),
  * saves a full-contour + TE-zoom comparison to configs/c3x_te_smoothness.png.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from bofm.geometry import parametrization as P
from bofm.geometry.profile import densify_profile

root = Path(__file__).resolve().parents[1]
profile = P.load_profile(root / "configs" / "c3x_coordinates.csv")
dense = densify_profile(profile)

raw_surf = P.build_surfaces(profile)
dense_surf = P.build_surfaces(dense)

print("points: raw=%d  densified=%d" % (profile.shape[0], dense.shape[0]))
print("arc length [mm]      raw      densified   ref")
for name, ref in (("suction", P.REF_SUCTION_ARC_MM), ("pressure", P.REF_PRESSURE_ARC_MM)):
    print("  %-9s %9.2f %11.2f %7.2f"
          % (name, raw_surf[name].arc_mm, dense_surf[name].arc_mm, ref))

# bounding box (axial x, tangential y) -- must be unchanged by densification
for tag, xy in (("raw", profile), ("densified", dense)):
    print("  %-9s bbox mm: x=%.2f  y=%.2f"
          % (tag, np.ptp(xy[:, 0]), np.ptp(xy[:, 1])))

# --- plot: full contour + TE zoom ------------------------------------------
te_i = int(np.argmax(profile[:, 0]))
te = profile[te_i]

fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12, 7))
for ax in (ax0, ax1):
    ax.plot(np.append(profile[:, 0], profile[0, 0]),
            np.append(profile[:, 1], profile[0, 1]),
            "-", color="tab:red", lw=1.0, marker="o", ms=3,
            label="raw polyline (78 pts)")
    ax.plot(np.append(dense[:, 0], dense[0, 0]),
            np.append(dense[:, 1], dense[0, 1]),
            "-", color="tab:blue", lw=1.2, label="densified spline")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("x [mm] (axial)")
    ax.set_ylabel("y [mm] (tangential)")

ax0.legend(loc="best")
ax0.set_title("Full C3X contour")
pad = 6.0
ax1.set_xlim(te[0] - pad, te[0] + 1.5)
ax1.set_ylim(te[1] - pad, te[1] + pad)
ax1.set_title("Trailing edge (zoom)")

out = root / "configs" / "c3x_te_smoothness.png"
fig.savefig(out, dpi=130, bbox_inches="tight")
print("\nsaved:", out)
