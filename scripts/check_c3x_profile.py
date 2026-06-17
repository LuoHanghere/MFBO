"""Sanity-check the digitized C3X profile and render it."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

csv = Path(__file__).resolve().parents[1] / "configs" / "c3x_coordinates.csv"
df = pd.read_csv(csv, comment="#")
x, y = df["x_mm"].to_numpy(), df["y_mm"].to_numpy()

closure_gap = np.hypot(x[0] - x[-1], y[0] - y[-1])
print(f"points        : {len(x)}")
print(f"x range (mm)  : {x.min():.3f} .. {x.max():.3f}  (axial chord ~78.16)")
print(f"y range (mm)  : {y.min():.3f} .. {y.max():.3f}")
print(f"LE-TE gap closure (pt1->pt78), mm: {closure_gap:.3f}")

fig, ax = plt.subplots(figsize=(6, 7))
ax.plot(np.append(x, x[0]), np.append(y, y[0]), "-o", ms=2, lw=1)
ax.plot(x[0], y[0], "gs", label="pt 1 (LE)")
ax.plot(x[29], y[29], "r^", label="pt 30 (TE)")
ax.set_aspect("equal")
ax.set_xlabel("x [mm] (axial)")
ax.set_ylabel("y [mm] (tangential)")
ax.set_title("NASA C3X vane profile (CR-174827 Table II)")
ax.legend()
ax.grid(True, alpha=0.3)
out = Path(__file__).resolve().parents[1] / "configs" / "c3x_profile.png"
fig.savefig(out, dpi=130, bbox_inches="tight")
print(f"saved: {out}")
