"""Single-airfoil external-flow domain for the film-cooled C3X vane (Kumar-style).

Flow field around ONE complete vane, shaped like the bent duct in Kumar et al.
(NASA-C3X, Springer 2022, Fig. 2): a straight axial inlet leg, a smooth bend that
follows the vane, and a straight outlet leg along the exit-flow direction.

Centreline construction (kept deliberately clean so the offset walls are smooth,
not wavy):
  - a clamped cubic spline through a FEW camber anchor points, with end tangents
    forced to the axial inflow and the exit-flow direction -> follows the vane
    but has no digitisation wiggle;
  - straight inlet leg (axial) and straight outlet leg (exit angle) attached C1.
The current default uses a curved duct: a smooth centreline follows the vane and
the two pitchwise periodic side walls are the same curve translated by the
physical C3X pitch in global y. This keeps the inlet and outlet parallel to y,
preserves the physical cascade placement, and retains an exact translational
pair without expanding the whole flow field into a rectangular box. The vane is
an inner cutout.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline, splev, splprep

from .parametrization import Surface


@dataclass
class ExternalFlowDomain:
    outer_loop_xy: np.ndarray
    airfoil_xy: np.ndarray
    centerline_xy: np.ndarray
    side_lower_xy: np.ndarray
    side_upper_xy: np.ndarray
    inlet_xy: np.ndarray
    outlet_xy: np.ndarray
    # Legacy consumers use pitch_mm as the translational-periodic distance.
    # For constant-y domains this may be wider than the physical cascade pitch,
    # because the complete C3X vane is taller in global y than one pitch.
    pitch_mm: float
    physical_pitch_mm: float
    periodic_width_mm: float
    periodic_translation_xy_mm: tuple[float, float]
    y_low: float | None
    y_high: float | None
    x_in: float
    x_out: float
    min_wall_clearance_mm: float


def _resample(xy, n):
    f = np.linspace(0.0, 1.0, len(xy))
    g = np.linspace(0.0, 1.0, n)
    return np.column_stack([np.interp(g, f, xy[:, 0]), np.interp(g, f, xy[:, 1])])


def _clamped_spline(anchors, t_in, t_out, n):
    # arc-length parameter -> clamped end derivative is the UNIT tangent.
    seg = np.linalg.norm(np.diff(anchors, axis=0), axis=1)
    t = np.concatenate([[0.0], np.cumsum(seg)])
    csx = CubicSpline(t, anchors[:, 0], bc_type=((1, t_in[0]), (1, t_out[0])))
    csy = CubicSpline(t, anchors[:, 1], bc_type=((1, t_in[1]), (1, t_out[1])))
    tt = np.linspace(0.0, t[-1], n)
    return np.column_stack([csx(tt), csy(tt)])


def _trim_to_plane(poly, pt, normal):
    s = (poly - pt) @ normal
    out = [poly[0]]
    for i in range(1, len(poly)):
        if (s[i - 1] <= 0 < s[i]) or (s[i - 1] >= 0 > s[i]):
            a = s[i - 1] / (s[i - 1] - s[i])
            out.append(poly[i - 1] + a * (poly[i] - poly[i - 1]))
            break
        out.append(poly[i])
    return np.array(out)


def _remove_consecutive_duplicates(poly, tol=1.0e-9):
    out = [np.asarray(poly[0], dtype=float)]
    for p in np.asarray(poly[1:], dtype=float):
        if np.linalg.norm(p - out[-1]) > tol:
            out.append(p)
    if np.linalg.norm(out[0] - out[-1]) > tol:
        out.append(out[0])
    return np.asarray(out, dtype=float)


def build_airfoil_external_domain(
    surfaces: dict[str, Surface], *, pitch_mm: float, axial_chord_mm: float,
    up_chord: float = 1.5, down_chord: float = 1.0,
    inlet_angle_deg: float = 0.0, exit_angle_deg: float = -72.38,
    n_anchor: int = 6, n: int = 240,
    sidewall_mode: str = "translated_centerline",
    channel_width_mm: float | None = None,
    translation_x_fraction: float = 0.0,
    wall_clearance_mm: float = 30.0,
    constant_y_margin_fraction: float = 0.125,
    constant_y_margin_mm: float | None = None,
) -> ExternalFlowDomain:
    suc = surfaces["suction"].xy
    pre = surfaces["pressure"].xy
    le, te = suc[0], suc[-1]
    airfoil = np.vstack([suc, pre[::-1][1:]])
    if not np.allclose(airfoil[0], airfoil[-1]):
        airfoil = np.vstack([airfoil, airfoil[0]])

    physical_pitch_mm = float(pitch_mm)
    x_in = le[0] - up_chord * axial_chord_mm
    x_out = te[0] + down_chord * axial_chord_mm
    t_in = np.array([np.cos(np.radians(inlet_angle_deg)), np.sin(np.radians(inlet_angle_deg))])
    t_out = np.array([np.cos(np.radians(exit_angle_deg)), np.sin(np.radians(exit_angle_deg))])

    # smoothed camber, then a FEW anchor points on it (avoids high-freq wiggle)
    cam = 0.5 * (_resample(suc, n) + _resample(pre, n))
    tck, _ = splprep([cam[:, 0], cam[:, 1]], s=1500.0, k=3)
    cam_s = np.array(splev(np.linspace(0.0, 1.0, 200), tck)).T
    idx = np.linspace(0, len(cam_s) - 1, n_anchor).astype(int)
    anchors = cam_s[idx]

    # bend = clamped spline LE..TE with axial start tangent and exit-angle end tangent
    bend = _clamped_spline(anchors, t_in, t_out, n)

    # straight legs (axial in, exit-angle out)
    up_pt = np.array([x_in, le[1] - (le[0] - x_in) * (t_in[1] / t_in[0])])
    s_out = (x_out - te[0]) / t_out[0] * 1.7
    dn_pt = te + s_out * t_out
    # straight legs need few points (they are straight); the bend carries the
    # resolution. Keeps the sketch light so headless SpaceClaim stays fast.
    up = np.linspace(up_pt, bend[0], 30)
    dn = np.linspace(bend[-1], dn_pt, 160)
    center = np.vstack([up[:-1], bend, dn[1:]])

    nx = np.array([1.0, 0.0])
    center = _trim_to_plane(center, np.array([x_out, 0.0]), nx)
    mode = sidewall_mode.strip().lower().replace("-", "_")
    if mode == "translated_centerline":
        # The two walls represent adjacent cascade passages. In these global
        # coordinates the physical blade pitch is parallel to y, never x.
        if channel_width_mm is not None and not np.isclose(
            float(channel_width_mm), physical_pitch_mm, rtol=0.0, atol=1.0e-9
        ):
            raise ValueError(
                "channel_width_mm must equal pitch_mm for a physical C3X "
                "pitch-periodic passage"
            )
        if not np.isclose(float(translation_x_fraction), 0.0, rtol=0.0, atol=1.0e-12):
            raise ValueError(
                "translation_x_fraction must be zero: C3X pitch periodicity "
                "is parallel to global y"
            )
        periodic_width = physical_pitch_mm
        translation = np.array([0.0, periodic_width], dtype=float)
        upper = center + 0.5 * translation
        lower = center - 0.5 * translation
        y_low = None
        y_high = None
    elif mode == "constant_y":
        margin = (
            float(constant_y_margin_mm)
            if constant_y_margin_mm is not None
            else float(constant_y_margin_fraction) * physical_pitch_mm
        )
        if margin < 0.0:
            raise ValueError("constant-y margin must be non-negative")
        y_low = float(np.min(airfoil[:, 1]) - margin)
        y_high = float(np.max(airfoil[:, 1]) + margin)
        periodic_width = y_high - y_low
        if periodic_width < physical_pitch_mm:
            extra = 0.5 * (physical_pitch_mm - periodic_width)
            y_low -= extra
            y_high += extra
            periodic_width = physical_pitch_mm
        y_mid = 0.5 * (y_low + y_high)
        center = np.array([[x_in, y_mid], [x_out, y_mid]], dtype=float)
        lower = np.array([[x_in, y_low], [x_out, y_low]], dtype=float)
        upper = np.array([[x_in, y_high], [x_out, y_high]], dtype=float)
        translation = np.array([0.0, periodic_width], dtype=float)
    else:
        raise ValueError(
            "sidewall_mode must be 'constant_y' or 'translated_centerline'"
        )

    inlet = np.array([lower[0], upper[0]])
    outlet = np.array([lower[-1], upper[-1]])
    outer = _remove_consecutive_duplicates(
        np.vstack([lower, outlet, upper[::-1], lower[0]])
    )

    def _min_dist(poly):
        seg = np.diff(poly, axis=0)
        d = []
        for p in airfoil[::4]:
            w = p - poly[:-1]
            tcl = np.clip(np.einsum("ij,ij->i", w, seg) /
                          (np.einsum("ij,ij->i", seg, seg) + 1e-12), 0, 1)
            proj = poly[:-1] + tcl[:, None] * seg
            d.append(np.min(np.linalg.norm(p - proj, axis=1)))
        return float(np.min(d))
    clearance = min(_min_dist(upper), _min_dist(lower))

    return ExternalFlowDomain(
        outer,
        airfoil,
        center,
        lower,
        upper,
        inlet,
        outlet,
        float(periodic_width),
        float(physical_pitch_mm),
        float(periodic_width),
        (float(translation[0]), float(translation[1])),
        float(y_low) if y_low is not None else None,
        float(y_high) if y_high is not None else None,
        float(x_in),
        float(x_out),
        clearance,
    )
