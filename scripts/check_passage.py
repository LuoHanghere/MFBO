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
from bofm.geometry.profile import densify_profile
from bofm.geometry.passage import build_passage


def _signed_area(xy: np.ndarray) -> float:
    x, y = xy[:, 0], xy[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _orient(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _segments_intersect(a: np.ndarray, b: np.ndarray,
                        c: np.ndarray, d: np.ndarray,
                        tol: float = 1e-9) -> bool:
    def on_segment(p, q, r):
        return (min(p[0], r[0]) - tol <= q[0] <= max(p[0], r[0]) + tol and
                min(p[1], r[1]) - tol <= q[1] <= max(p[1], r[1]) + tol)

    o1 = _orient(a, b, c)
    o2 = _orient(a, b, d)
    o3 = _orient(c, d, a)
    o4 = _orient(c, d, b)
    if o1 * o2 < -tol and o3 * o4 < -tol:
        return True
    if abs(o1) <= tol and on_segment(a, c, b):
        return True
    if abs(o2) <= tol and on_segment(a, d, b):
        return True
    if abs(o3) <= tol and on_segment(c, a, d):
        return True
    if abs(o4) <= tol and on_segment(c, b, d):
        return True
    return False


def _self_intersections(loop_xy: np.ndarray) -> list[tuple[int, int]]:
    pts = loop_xy[:-1] if np.allclose(loop_xy[0], loop_xy[-1]) else loop_xy
    n = len(pts)
    hits: list[tuple[int, int]] = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if j in (i, (i - 1) % n, (i + 1) % n):
                continue
            if i == 0 and j == n - 1:
                continue
            c, d = pts[j], pts[(j + 1) % n]
            if _segments_intersect(a, b, c, d):
                hits.append((i, j))
    return hits


def _periodic_pair_error(a: np.ndarray, b: np.ndarray,
                         pitch_mm: float) -> float:
    offset = np.array([0.0, pitch_mm])
    same = np.max(np.linalg.norm((a + offset) - b, axis=1))
    flipped = np.max(np.linalg.norm((a[::-1] + offset) - b, axis=1))
    return float(min(same, flipped))


def passage_diagnostics(pas) -> dict:
    loop = pas.loop_xy
    dseg = np.linalg.norm(np.diff(loop, axis=0), axis=1)
    hits = _self_intersections(loop)
    return {
        "closed_gap_mm": float(np.linalg.norm(loop[0] - loop[-1])),
        "signed_area_mm2": _signed_area(loop),
        "min_segment_mm": float(dseg.min()),
        "max_segment_mm": float(dseg.max()),
        "self_intersections": hits,
        "upstream_periodic_pair_error_mm": _periodic_pair_error(
            pas.segments["periodic_up_lower"],
            pas.segments["periodic_up_upper"],
            pas.pitch_mm,
        ),
        "downstream_periodic_pair_error_mm": _periodic_pair_error(
            pas.segments["periodic_down_lower"],
            pas.segments["periodic_down_upper"],
            pas.pitch_mm,
        ),
    }

root = Path(__file__).resolve().parents[1]
config = yaml.safe_load(open(root / "configs" / "c3x_baseline.yaml", encoding="utf-8"))
geom = config["geometry"]
source_profile = P.load_profile(root / "configs" / "c3x_coordinates.csv")
raw_profile = P.clean_profile(source_profile)
profile = densify_profile(raw_profile, n_per_surface=220, cluster=0.5)
raw_surfaces = P.build_surfaces(raw_profile)
surfaces = P.build_surfaces(profile)

pd = geom.get("passage_domain", {})
exit_deg = pd.get("downstream_periodic_angle_deg")
if exit_deg is None:
    # legacy: negate NASA magnitude if only the unsigned table value exists
    exit_deg = -abs(float(geom["air_exit_angle_deg"]))

pas = build_passage(surfaces,
                    pitch_mm=geom["pitch_mm"],
                    axial_chord_mm=geom["axial_chord_mm"],
                    up_chord=pd.get("upstream_axial_chords", 1.0),
                    down_chord=pd.get("downstream_axial_chords", 1.0),
                    inlet_angle_deg=0.0,
                    exit_angle_deg=float(exit_deg))

print("pitch          : %.2f mm" % pas.pitch_mm)
print("x_in / x_out   : %.1f / %.1f mm" % (pas.x_in, pas.x_out))
print("loop points    : %d" % len(pas.loop_xy))
print("profile points : source_raw=%d cleaned_raw=%d densified=%d" %
      (len(source_profile), len(raw_profile), len(profile)))
print("arc raw/dense  : suction %.2f/%.2f mm, pressure %.2f/%.2f mm" %
      (raw_surfaces["suction"].arc_mm, surfaces["suction"].arc_mm,
       raw_surfaces["pressure"].arc_mm, surfaces["pressure"].arc_mm))

diag = passage_diagnostics(pas)
print("diagnostics    : closed_gap=%.3g mm, min_seg=%.3g mm, "
      "periodic_pair_err(up/down)=%.3g/%.3g mm, self_intersections=%d" %
      (diag["closed_gap_mm"], diag["min_segment_mm"],
       diag["upstream_periodic_pair_error_mm"],
       diag["downstream_periodic_pair_error_mm"],
       len(diag["self_intersections"])))
if diag["closed_gap_mm"] > 1e-6 or diag["self_intersections"]:
    raise SystemExit("passage geometry failed validity checks")

# export the passage loop for the SpaceClaim journal
passage_json = root / "configs" / "c3x_passage.json"
json.dump({
    "case": config["case"]["name"],
    "units": "mm",
    "span_mm": geom["span_mm"],
    "pitch_mm": pas.pitch_mm,
    "x_in": pas.x_in, "x_out": pas.x_out,
    "profile_points": {
        "source_raw": int(len(source_profile)),
        "cleaned_raw": int(len(raw_profile)),
        "densified": int(len(profile)),
    },
    "surface_arc_mm": {
        "raw": {name: float(s.arc_mm) for name, s in raw_surfaces.items()},
        "densified": {name: float(s.arc_mm) for name, s in surfaces.items()},
    },
    "diagnostics": diag,
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
ax.plot(np.append(raw_profile[:, 0], raw_profile[0, 0]),
        np.append(raw_profile[:, 1], raw_profile[0, 1]),
        color="tab:red", lw=0.8, alpha=0.45, zorder=5,
        label="raw profile")

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
