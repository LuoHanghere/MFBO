"""Verify the parametrization: arc lengths vs NASA Table III + plot baseline holes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from bofm.geometry import parametrization as P
from bofm.geometry.profile import densify_profile

root = Path(__file__).resolve().parents[1]
config = yaml.safe_load(open(root / "configs" / "c3x_baseline.yaml", encoding="utf-8"))
profile = P.load_profile(root / "configs" / "c3x_coordinates.csv")
surfaces = P.build_surfaces(profile)  # raw profile drives all validation below

print("computed suction arc : %.2f mm  (ref %.2f)" % (surfaces["suction"].arc_mm, P.REF_SUCTION_ARC_MM))
print("computed pressure arc: %.2f mm  (ref %.2f)" % (surfaces["pressure"].arc_mm, P.REF_PRESSURE_ARC_MM))
err = P.validate_arcs(surfaces)
print("arc errors [mm]:", {k: round(v, 2) for k, v in err.items()})

holes = P.place_holes(config, surfaces)
print("\nbaseline hole placements:")
for h in holes:
    flag = " (FIXED)" if h.fixed else ""
    print(f"  {h.row_id:3s} {h.surface:8s} s/s0={h.s_frac:.3f} "
          f"-> (x={h.x_mm:6.2f}, y={h.y_mm:6.2f}) mm, surf_tan={h.tangent_deg:7.2f} deg, "
          f"alpha={h.injection_deg:.0f} deg, p/D={h.p_over_D:.1f}{flag}")

print("\nfeasibility (baseline):", P.check_feasibility(holes, config, surfaces) or "OK")

# deliberately-infeasible perturbations to confirm the checks fire
bad = P.place_holes(config, surfaces, design={
    "SS1": {"s_over_s0": 0.280},          # crosses SS2 (ordering + bounds)
    "PS1": {"p_over_D": 2.0, "alpha_deg": 60},  # below/above bounds
})
print("feasibility (perturbed):")
for msg in P.check_feasibility(bad, config, surfaces):
    print("  -", msg)

# Embed the DENSIFIED contour so the SpaceClaim journal's straight-segment build
# follows a smooth curve (the raw 78-pt polyline facets the high-curvature TE).
# Validation above still uses the raw profile, so the NASA arc check is unaffected.
dense_profile = densify_profile(profile)
out_json = P.export_placements(holes, config, root / "configs" / "c3x_placements_baseline.json",
                               profile=dense_profile)
print("\nwrote:", out_json, "(profile_xy_mm: %d densified pts)" % len(dense_profile))

# plot
fig, ax = plt.subplots(figsize=(6, 7))
px, py = profile[:, 0], profile[:, 1]
ax.plot(np.append(px, px[0]), np.append(py, py[0]), "-", color="0.6", lw=1)
for surf, col in (("suction", "tab:blue"), ("pressure", "tab:green")):
    s = surfaces[surf]
    ax.plot(s.xy[:, 0], s.xy[:, 1], col, lw=2, alpha=0.5, label=f"{surf} ({s.arc_mm:.0f} mm)")
for h in holes:
    mk = "x" if h.fixed else "o"
    c = "red" if not h.fixed else "0.4"
    ax.plot(h.x_mm, h.y_mm, mk, color=c, ms=10, mew=2)
    ax.annotate(h.row_id, (h.x_mm, h.y_mm), textcoords="offset points", xytext=(6, 6))
ax.set_aspect("equal"); ax.legend(); ax.grid(True, alpha=0.3)
ax.set_xlabel("x [mm] (axial)"); ax.set_ylabel("y [mm] (tangential)")
ax.set_title("C3X baseline body-row hole placements (round-1: 3 free rows)")
out = root / "configs" / "c3x_holes_baseline.png"
fig.savefig(out, dpi=130, bbox_inches="tight")
print("\nsaved:", out)
