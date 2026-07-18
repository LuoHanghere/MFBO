# SpaceClaim IronPython journal (API V242) -- SINGLE-AIRFOIL EXTERNAL FLOW DOMAIN.
#
# Reads BOFM_EXTERNAL_FLOW_JSON (outer_loop_xy_mm + airfoil_xy_mm + x_in/x_out/
# pitch from scripts/check_external_flow.py) and BOFM_SPAN_MM. Sketches the outer
# duct boundary AND the vane as an inner cutout, extrudes the annular face to span
# -> a fluid prism with the complete vane cut out (whole perimeter wetted, so the
# user can later add LE/both-surface film holes). Classifies faces and writes the
# named selections Fluent Meshing needs:
#   inlet, outlet, periodic_low, periodic_high, span_low, span_high, vane_wall
# Saves BOFM_OUT_SCDOC (+ .sat/.fmd). This is the FIXED domain the user opens in
# SpaceClaim to draw the coolant plenums; film holes are added parametrically
# afterwards (separate journal reading a hole layout).
import os
import json
import math
import traceback

status_path = os.environ.get("BOFM_STATUS")
log = []
EPS = 0.5  # mm tolerance for plane/position tests


def finish(tag):
    if status_path:
        f = open(status_path, "w")
        f.write(tag + "\n" + "\n".join([str(x) for x in log]))
        f.close()


def bbox_mm(face):
    bb = face.Shape.GetBoundingBox(Matrix.Identity)
    mn, mx = bb.MinCorner, bb.MaxCorner
    return (mn.X * 1000, mn.Y * 1000, mn.Z * 1000,
            mx.X * 1000, mx.Y * 1000, mx.Z * 1000)


def make_ns(name, faces):
    if not faces:
        log.append("NS %s: SKIP (0 faces)" % name)
        return
    sel = FaceSelection.Create(faces)
    res = NamedSelection.Create(sel, Selection.Empty())
    grp = res.CreatedNamedSelection
    try:
        RenameObject.Execute(Selection.Create(grp), name)
        tag = "rename"
    except Exception:
        try:
            grp.SetName(name); tag = "SetName"
        except Exception as e2:
            tag = "FAILED:" + str(e2)
    log.append("NS %s: %d faces (%s)" % (name, len(faces), tag))


def clean_loop(loop):
    pts = [[float(p[0]), float(p[1])] for p in loop]
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts = pts[:-1]
    return pts


def sketch_loop(loop):
    pts = clean_loop(loop)
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        SketchLine.Create(Point.Create(MM(a[0]), MM(a[1]), MM(0)),
                          Point.Create(MM(b[0]), MM(b[1]), MM(0)))


def face_area_xy(face):
    x0, y0, z0, x1, y1, z1 = bbox_mm(face)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def largest_planar_face():
    best, area = None, -1.0
    for bi in range(GetRootPart().Bodies.Count):
        bd = GetRootPart().Bodies[bi]
        for fi in range(bd.Faces.Count):
            a = face_area_xy(bd.Faces[fi])
            if a > area:
                best, area = bd.Faces[fi], a
    return best


def dist_pt_to_polyline(px, py, poly):
    best = 1.0e18
    for k in range(len(poly) - 1):
        ax, ay = poly[k]
        bx, by = poly[k + 1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            t = 0.0
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / L2
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        qx, qy = ax + t * dx, ay + t * dy
        d = math.sqrt((px - qx) ** 2 + (py - qy) ** 2)
        if d < best:
            best = d
    return best


try:
    log.append("started")
    data = json.load(open(os.environ.get("BOFM_EXTERNAL_FLOW_JSON")))
    outer = data["outer_loop_xy_mm"]
    airfoil = [[float(p[0]), float(p[1])] for p in data["airfoil_xy_mm"]]
    if abs(airfoil[0][0] - airfoil[-1][0]) > 1e-9 or abs(airfoil[0][1] - airfoil[-1][1]) > 1e-9:
        airfoil_closed = airfoil + [airfoil[0]]
    else:
        airfoil_closed = airfoil
    x_in = float(data["x_in"])
    x_out = float(data["x_out"])
    pitch = float(data.get("periodic_width_mm", data.get("pitch_mm")))
    span_env = os.environ.get("BOFM_SPAN_MM")
    span = float(span_env) if span_env else float(data.get("span_mm", 76.2))
    log.append("loaded outer=%d airfoil=%d span=%.3f pitch=%.2f x_in=%.1f x_out=%.1f"
               % (len(outer), len(airfoil), span, pitch, x_in, x_out))

    # sketch outer duct boundary + vane as an inner hole, then fill -> annular face
    ViewHelper.SetSketchPlane(Plane.PlaneXY)
    sketch_loop(outer)
    sketch_loop(airfoil)
    ViewHelper.SetViewMode(InteractionMode.Solid)
    log.append("filled: bodies=%d" % GetRootPart().Bodies.Count)

    face = largest_planar_face()
    if face is None:
        raise Exception("no planar face after fill")
    sel = FaceSelection.Create(face)
    options = ExtrudeFaceOptions()
    options.ExtrudeType = ExtrudeType.Add
    ExtrudeFaces.Execute(sel, MM(span), options)
    body = GetRootPart().Bodies[0]
    log.append("extruded: bodies=%d faces=%d"
               % (GetRootPart().Bodies.Count, body.Faces.Count))

    # --- classify faces -----------------------------------------------------
    inlet, outlet, span_lo, span_hi, walls = [], [], [], [], []
    periodic = []
    for idx in range(body.Faces.Count):
        f = body.Faces[idx]
        x0, y0, z0, x1, y1, z1 = bbox_mm(f)
        cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        if dz < EPS:                                       # z-plane -> span cap
            (span_lo if cz < span * 0.5 else span_hi).append(f)
        elif dx < EPS and dy > 0.5 * pitch and abs(cx - x_in) < EPS:
            inlet.append(f)                                # full-pitch vertical face
        elif dx < EPS and dy > 0.5 * pitch and abs(cx - x_out) < EPS:
            outlet.append(f)
        elif dist_pt_to_polyline(cx, cy, airfoil_closed) < 5.0:
            walls.append(f)                                # on the vane contour
        else:
            periodic.append((f, cx, cy))                   # outer side walls

    # Split periodic faces into low/high independently: upper = lower + (0,pitch)
    # exactly, so a face is LOW if a periodic face exists one pitch above it, HIGH
    # if one exists a pitch below. (Greedy mutual pairing left a few unmatched.)
    per_lo, per_hi = [], []
    for i in range(len(periodic)):
        fi, cxi, cyi = periodic[i]
        has_above = has_below = False
        for j in range(len(periodic)):
            if j == i:
                continue
            cxj, cyj = periodic[j][1], periodic[j][2]
            if abs(cxj - cxi) < EPS and abs((cyi + pitch) - cyj) < 3.0:
                has_above = True
            if abs(cxj - cxi) < EPS and abs((cyi - pitch) - cyj) < 3.0:
                has_below = True
        if has_above and not has_below:
            per_lo.append(fi)
        elif has_below and not has_above:
            per_hi.append(fi)
        else:
            # ambiguous (both/neither): fall back to side of mid-pitch
            (per_lo if cyi < 0.0 else per_hi).append(fi)
    log.append("classified: inlet=%d outlet=%d span_lo=%d span_hi=%d "
               "periodic=%d (lo=%d,hi=%d) vane_wall=%d"
               % (len(inlet), len(outlet), len(span_lo), len(span_hi),
                  len(periodic), len(per_lo), len(per_hi), len(walls)))

    make_ns("inlet", inlet)
    make_ns("outlet", outlet)
    make_ns("periodic_low", per_lo)
    make_ns("periodic_high", per_hi)
    make_ns("span_low", span_lo)
    make_ns("span_high", span_hi)
    make_ns("vane_wall", walls)

    out = os.environ.get("BOFM_OUT_SCDOC")
    if out:
        DocumentSave.Execute(out)
        log.append("saved: " + out)
        base = out[:-6] if out.endswith(".scdoc") else out
        for ext in (".sat", ".fmd"):
            try:
                DocumentSave.Execute(base + ext)
                log.append("exported %s -> exists=%s" % (ext, os.path.exists(base + ext)))
            except Exception as ee:
                log.append("export %s FAILED: %s" % (ext, str(ee)[:140]))

    ok = (len(inlet) > 0 and len(outlet) > 0 and len(walls) > 0 and
          len(per_lo) == len(per_hi) and len(per_lo) > 0)
    finish("OK" if ok else "ERROR")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
