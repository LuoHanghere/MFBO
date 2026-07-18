# SpaceClaim IronPython journal (API V242) -- EXTRACT COOLANT-CAVITY SECTIONS.
#
# Opens BOFM_IN_SCDOC and writes BOFM_OUT_JSON with each coolant cavity's XY
# section polygon. Handles two cases:
#   (a) NAMED 3D plenum solids (SS_plenum / PS_plenum / LE_plenum) -- the current
#       workflow: take each body's z~0 cap face boundary; role = body name.
#   (b) planar z~0 sketch surfaces (legacy) -- footprint smaller than the flow
#       solid; role assigned by position (LE=min x, SS=high y, PS=low y).
import os
import json
import math
import traceback

status_path = os.environ.get("BOFM_STATUS")
log = []
PLENUM_NAMES = ("SS_plenum", "PS_plenum", "LE_plenum")


def finish(tag):
    if status_path:
        f = open(status_path, "w")
        f.write(tag + "\n" + "\n".join([unicode(x) for x in log]))
        f.close()


def bbox_mm(shape_owner):
    bb = shape_owner.Shape.GetBoundingBox(Matrix.Identity)
    mn, mx = bb.MinCorner, bb.MaxCorner
    return (mn.X * 1000, mn.Y * 1000, mn.Z * 1000,
            mx.X * 1000, mx.Y * 1000, mx.Z * 1000)


def all_bodies():
    out = []
    def walk(part):
        for i in range(part.Bodies.Count):
            out.append(part.Bodies[i])
        for j in range(part.Components.Count):
            walk(part.Components[j].Content)
    walk(GetRootPart())
    return out


def sample_face_boundary(face, n_per_edge=16):
    pts = []
    for ei in range(face.Edges.Count):
        e = face.Edges[ei]
        for k in range(n_per_edge + 1):
            t = float(k) / n_per_edge
            try:
                p = e.EvalProportion(t).Point
                pts.append((p.X * 1000.0, p.Y * 1000.0))
            except Exception:
                pass
    return pts


def order_by_angle(pts):
    if not pts:
        return pts
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    uniq = []
    for p in sorted(pts, key=lambda q: math.atan2(q[1] - cy, q[0] - cx)):
        if not uniq or (abs(p[0] - uniq[-1][0]) > 1e-4 or abs(p[1] - uniq[-1][1]) > 1e-4):
            uniq.append(p)
    return uniq


def cap_face_z0(body):
    """Return the planar (xy) face nearest z=0 -- the cavity cross-section."""
    best, best_z = None, 1e9
    for fi in range(body.Faces.Count):
        f = body.Faces[fi]
        fb = bbox_mm(f)
        dz = fb[5] - fb[2]
        if dz < 0.1:                      # planar in xy
            zc = 0.5 * (fb[2] + fb[5])
            if abs(zc) < best_z:
                best, best_z = f, abs(zc)
    return best


try:
    log.append("started")
    inp = os.environ.get("BOFM_IN_SCDOC")
    DocumentOpen.Execute(inp)
    log.append("opened: " + inp)

    bodies = all_bodies()
    log.append("bodies=%d" % len(bodies))
    cavities = []
    named_found = False
    for bi, bd in enumerate(bodies):
        try:
            name = bd.GetName()
        except Exception:
            name = "?"
        b = bbox_mm(bd)
        dz = b[5] - b[2]
        foot = (b[3] - b[0]) * (b[4] - b[1])
        log.append("body[%d] name=%r bbox x[%.1f,%.1f] y[%.1f,%.1f] z[%.2f,%.2f] dz=%.3f faces=%d"
                   % (bi, name, b[0], b[3], b[1], b[4], b[2], b[5], dz, bd.Faces.Count))

        face = None
        role = None
        if name in PLENUM_NAMES:                 # (a) named 3D plenum solid
            named_found = True
            face = cap_face_z0(bd)
            role = name
            log.append("  named plenum -> cap face %s" % ("found" if face else "MISSING"))
        elif dz < 0.1 and bd.Faces.Count >= 1 and foot < 8000.0:   # (b) planar sketch
            face = bd.Faces[0]

        if face is not None:
            poly = order_by_angle(sample_face_boundary(face))
            if len(poly) >= 3:
                cx = sum(p[0] for p in poly) / len(poly)
                cy = sum(p[1] for p in poly) / len(poly)
                rec = {"name": name, "centroid_xy_mm": [cx, cy],
                       "bbox_xy_mm": [b[0], b[1], b[3], b[4]],
                       "profile_xy_mm": [[p[0], p[1]] for p in poly]}
                if role:
                    rec["role"] = role
                cavities.append(rec)
                log.append("  -> cavity captured: %d pts, centroid=(%.1f,%.1f)" % (len(poly), cx, cy))

    # legacy positional roles only if bodies were not named
    if cavities and not named_found:
        le = min(cavities, key=lambda c: c["centroid_xy_mm"][0]); le["role"] = "LE_plenum"
        rest = sorted([c for c in cavities if c is not le], key=lambda c: c["centroid_xy_mm"][1])
        if rest:
            rest[-1]["role"] = "SS_plenum"
        if len(rest) >= 2:
            rest[0]["role"] = "PS_plenum"

    out_json = os.environ.get("BOFM_OUT_JSON")
    if out_json:
        f = open(out_json, "w")
        f.write(json.dumps({"units": "mm", "source": inp, "cavities": cavities}, indent=2))
        f.close()
        log.append("wrote: " + out_json + " (%d cavities)" % len(cavities))

    finish("OK" if cavities else "ERROR")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
