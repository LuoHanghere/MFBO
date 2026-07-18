"""Densify + smooth the 2D vane contour so straight-segment CAD builds look smooth.

The SpaceClaim journal builds the airfoil by connecting consecutive contour
points with straight ``SketchLine`` segments. With only the raw 78 NASA points
this faceting is visible at high-curvature regions (notably the trailing edge).

The fix here is purely upstream/CPython: interpolate the SUCTION and PRESSURE
surfaces SEPARATELY (each LE->TE, parameterized by cumulative arc length),
resample each with cosine ("Chebyshev-like") spacing that concentrates points
near the LE and TE, then stitch the two resampled surfaces back into one closed
contour. Interpolating the surfaces separately (rather than one periodic curve
through all 78 points) avoids cross-LE/TE coupling.

A shape-preserving PCHIP interpolant is used (not a natural cubic): PCHIP is
monotone between data points, so x(t) and y(t) never overshoot the local data
range. This keeps the bounding box and the genuine small-radius trailing edge
intact (a plain cubic spline bulges ~0.6 mm past the true TE), while still
removing the visible polyline faceting.

The densified curve passes through the original LE/TE and closely follows every
raw point -- it removes the polyline faceting WITHOUT rounding away the genuine
trailing edge.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import PchipInterpolator

from .parametrization import Surface, build_surfaces, clean_profile


def _clustered_spacing(n: int, strength: float) -> np.ndarray:
    """Return ``n`` parameters in [0, 1] mildly clustered toward both ends.

    A pure cosine (Chebyshev) distribution clusters so aggressively that the end
    segments shrink quadratically (to a few microns here), which is below the CAD
    kernel's coincidence tolerance and breaks loop closure. Blending cosine with
    uniform spacing (``strength`` in [0, 1]; 0 = uniform, 1 = full cosine) keeps a
    mild LE/TE refinement while guaranteeing a healthy minimum segment length.
    """
    i = np.arange(n)
    uniform = i / (n - 1)
    cosine = 0.5 * (1.0 - np.cos(np.pi * i / (n - 1)))
    return (1.0 - strength) * uniform + strength * cosine


def _spline_surface(surf: Surface, n_pts: int, cluster: float) -> np.ndarray:
    """Resample one LE->TE surface via an arc-length PCHIP fit + end clustering."""
    s = surf.s
    # Drop any zero-length segments (duplicate points) -- they would make the
    # arc-length parameter non-strictly-increasing and break the interpolant.
    keep = np.concatenate([[True], np.diff(s) > 1e-9])
    s_u = s[keep]
    xy_u = surf.xy[keep]
    t = s_u / s_u[-1]
    fx = PchipInterpolator(t, xy_u[:, 0])
    fy = PchipInterpolator(t, xy_u[:, 1])
    tq = _clustered_spacing(n_pts, cluster)
    return np.column_stack([fx(tq), fy(tq)])


def densify_profile(profile: np.ndarray, n_per_surface: int = 220,
                    cluster: float = 0.5) -> np.ndarray:
    """Return a smooth, densified closed contour from the raw profile.

    Parameters
    ----------
    profile : (N, 2) array
        Raw closed contour (e.g. the 78 NASA points), any winding.
    n_per_surface : int
        Number of resampled points per surface (suction & pressure). The returned
        contour has ``2 * n_per_surface - 2`` points (shared LE/TE not duplicated).
    cluster : float
        LE/TE clustering strength in [0, 1] (0 = uniform arc length, 1 = full
        cosine). The default keeps a mild refinement without producing
        sub-tolerance (degenerate) segments at the LE/TE.

    The suction/pressure split, LE/TE detection, and arc-length parametrization
    all reuse :func:`bofm.geometry.parametrization.build_surfaces`, so the
    densified contour stays consistent with the validated geometry.
    """
    profile = clean_profile(profile)
    surfaces = build_surfaces(profile)
    suc = _spline_surface(surfaces["suction"], n_per_surface, cluster)
    pre = _spline_surface(surfaces["pressure"], n_per_surface, cluster)
    # Stitch: suction LE->TE, then pressure TE->LE with shared TE/LE dropped so
    # the closed loop has no duplicate (zero-length) segments.
    return np.vstack([suc, pre[::-1][1:-1]])
