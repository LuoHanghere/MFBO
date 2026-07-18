# SpaceClaim IronPython journal (API V242) -- EXTERNAL FLOW + COOLANT CAVITIES.
#
# Reads BOFM_EXTERNAL_FLOW_JSON (outer duct loop + vane cutout) and
# BOFM_CAVITIES_JSON (the user-drawn plenum sections, extracted by
# extract_cavities.py) and BOFM_SPAN_MM. Sketches the duct boundary, the vane as
# a hole, and each cavity inside the vane; even-odd fill then yields the flow
# annulus + each cavity as separate faces while the vane metal stays void. The
# flow face and the cavity faces are extruded to span as independent fluid bodies:
#   fluid  +  SS_plenum / PS_plenum / LE_plenum
# Faces of the flow body get named (inlet/outlet/periodic_low/high/span_low/high/
# vane_wall); each cavity body is named. Saves BOFM_OUT_SCDOC (+ .sat/.fmd).
import os
import json
import math
import traceback

status_path = os.environ.get("BOFM_STATUS")
log = []
EPS = 0.5


def finish(tag):
    if status_path:
        f = open(status_path, "w")
        f.write(tag + "\n" + "\n".join([unicode(x) for x in log]))
        f.close()


def bbox_mm(owner):
    bb = owner.Shape.GetBoundingBox(Matrix.Identity)
    mn, mx = bb.MinCorner, bb.MaxCorner
    return (mn.X * 1000, mn.Y * 1000, mn.Z * 1000,
            mx.X * 1000, mx.Y * 1000, mx.Z * 1000)


def make_ns(name, faces):
    if not faces:
        log.append("NS %s: SKIP (0 faces)" % name)
        return
    res = NamedSelection.Create(FaceSelection.Create(faces), Selection.Empty())
    grp = res.CreatedNamedSelection
    try:
        RenameObject.Execute(Selection.Create(grp), name)
    except Exception:
        try:
            grp.SetName(name)
        except Exception:
            pass
    log.append("NS %s: %d faces" % (name, len(faces)))


def sketch_loop(loop):
    pts = [[float(p[0]), float(p[1])] for p in loop]
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts = pts[:-1]
    for i in range(len(pts)):
        a = pts[i]; b = pts[(i + 1) % len(pts)]
        SketchLine.Create(Point.Create(MM(a[0]), MM(a[1]), MM(0)),
                          Point.Create(MM(b[0]), MM(b[1]), MM(0)))


def face_area(face):
    x0, y0, z0, x1, y1, z1 = bbox_mm(face)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def face_centroid_xy(face):
    x0, y0, z0, x1, y1, z1 = bbox_mm(face)
    return (0.5 * (x0 + x1), 0.5 * (y0 + y1))


def rename_body(body, name):
    try:
        RenameObject.Execute(Selection.Create(body), name)
    except Exception:
        try:
            body.SetName(name)
        except Exception:
            pass


def dist_pt_poly(px, py, poly):
    best = 1e18
    for k in range(len(poly) - 1):
        ax, ay = poly[k]; bx, by = poly[k + 1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-12 else ((px - ax) * dx + (py - ay) * dy) / L2
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        d = math.sqrt((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2)
        if d < best:
            best = d
    return best


try:
    log.append("started")
    data = json.load(open(os.environ.get("BOFM_EXTERNAL_FLOW_JSON")))
    cav_doc = json.load(open(os.environ.get("BOFM_CAVITIES_JSON")))
    outer = data["outer_loop_xy_mm"]
    airfoil = [[float(p[0]), float(p[1])] for p in data["airfoil_xy_mm"]]
    if abs(airfoil[0][0] - airfoil[-1][0]) > 1e-9 or abs(airfoil[0][1] - airfoil[-1][1]) > 1e-9:
        airfoil_closed = airfoil + [airfoil[0]]
    else:
        airfoil_closed = airfoil
    x_in = float(data["x_in"])
    x_out = float(data["x_out"])
    pitch = float(data.get("periodic_width_mm", data.get("pitch_mm")))
    span = float(os.environ.get("BOFM_SPAN_MM", "76.2"))
    cavities = cav_doc["cavities"]
    log.append("flow outer=%d airfoil=%d cavities=%d span=%.2f"
               % (len(outer), len(airfoil), len(cavities), span))

    ViewHelper.SetSketchPlane(Plane.PlaneXY)
    sketch_loop(outer)
    sketch_loop(airfoil)
    for c in cavities:
        sketch_loop(c["profile_xy_mm"])
    ViewHelper.SetViewMode(InteractionMode.Solid)

    # collect planar faces produced by the fill
    faces = []
    for bi in range(GetRootPart().Bodies.Count):
        bd = GetRootPart().Bodies[bi]
        for fi in range(bd.Faces.Count):
            f = bd.Faces[fi]
            faces.append((f, face_area(f), face_centroid_xy(f)))
    faces.sort(key=lambda t: -t[1])
    log.append("fill faces=%d areas=%s" % (len(faces), [round(t[1], 1) for t in faces[:8]]))

    # flow face = largest; cavity faces = match cavity centroids; vane metal = skip
    flow_face = faces[0][0]
    to_extrude = [flow_face]
    cav_face_for = {}
    for c in cavities:
        cc = c["centroid_xy_mm"]
        best, bd = None, 1e18
        for f, a, cen in faces[1:]:
            d = math.sqrt((cen[0] - cc[0]) ** 2 + (cen[1] - cc[1]) ** 2)
            if d < bd:
                bd, best = d, f
        if best is not None and bd < 5.0:
            cav_face_for[c.get("role", c.get("name", "cav"))] = best
            to_extrude.append(best)
            log.append("cavity %s face matched dist=%.2f" % (c.get("role"), bd))
        else:
            log.append("cavity %s NO face match (best dist=%.2f)" % (c.get("role"), bd))

    options = ExtrudeFaceOptions()
    options.ExtrudeType = ExtrudeType.Add
    ExtrudeFaces.Execute(FaceSelection.Create(to_extrude), MM(span), options)
    log.append("extruded %d faces -> bodies=%d" % (len(to_extrude), GetRootPart().Bodies.Count))

    # delete any leftover planar surface bodies (the un-extruded vane-metal face)
    for bi in range(GetRootPart().Bodies.Count - 1, -1, -1):
        bd = GetRootPart().Bodies[bi]
        b = bbox_mm(bd)
        if (b[5] - b[2]) < 0.01:
            try:
                Delete.Execute(BodySelection.Create([bd]))
                log.append("deleted leftover surface body")
            except Exception:
                pass

    # identify bodies: flow = widest x-span; cavities = match centroid
    bodies = [GetRootPart().Bodies[i] for i in range(GetRootPart().Bodies.Count)]
    flow_body = max(bodies, key=lambda bd: (bbox_mm(bd)[3] - bbox_mm(bd)[0]))
    rename_body(flow_body, "fluid")
    for c in cavities:
        cc = c["centroid_xy_mm"]; role = c.get("role", c.get("name", "cav"))
        best, bd = None, 1e18
        for body in bodies:
            if body == flow_body:
                continue
            bb = bbox_mm(body); cen = (0.5 * (bb[0] + bb[3]), 0.5 * (bb[1] + bb[4]))
            d = math.sqrt((cen[0] - cc[0]) ** 2 + (cen[1] - cc[1]) ** 2)
            if d < bd:
                bd, best = d, body
        if best is not None and bd < 6.0:
            rename_body(best, role)
            log.append("named cavity body %s (dist=%.2f)" % (role, bd))

    # --- classify flow-body faces ------------------------------------------
    inlet, outlet, span_lo, span_hi, walls = [], [], [], [], []
    periodic = []
    for idx in range(flow_body.Faces.Count):
        f = flow_body.Faces[idx]
        x0, y0, z0, x1, y1, z1 = bbox_mm(f)
        cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        if dz < EPS:
            (span_lo if cz < span * 0.5 else span_hi).append(f)
        elif dx < EPS and dy > 0.5 * pitch and abs(cx - x_in) < EPS:
            inlet.append(f)
        elif dx < EPS and dy > 0.5 * pitch and abs(cx - x_out) < EPS:
            outlet.append(f)
        elif dist_pt_poly(cx, cy, airfoil_closed) < 5.0:
            walls.append(f)
        else:
            periodic.append((f, cx, cy))

    per_lo, per_hi = [], []
    for i in range(len(periodic)):
        fi, cxi, cyi = periodic[i]
        above = below = False
        for j in range(len(periodic)):
            if j == i:
                continue
            cxj, cyj = periodic[j][1], periodic[j][2]
            if abs(cxj - cxi) < EPS and abs((cyi + pitch) - cyj) < 3.0:
                above = True
            if abs(cxj - cxi) < EPS and abs((cyi - pitch) - cyj) < 3.0:
                below = True
        if above and not below:
            per_lo.append(fi)
        elif below and not above:
            per_hi.append(fi)
        else:
            (per_lo if cyi < 0.0 else per_hi).append(fi)
    log.append("flow faces: inlet=%d outlet=%d span_lo=%d span_hi=%d periodic(lo=%d,hi=%d) vane_wall=%d"
               % (len(inlet), len(outlet), len(span_lo), len(span_hi),
                  len(per_lo), len(per_hi), len(walls)))

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
                log.append("export %s FAILED: %s" % (ext, str(ee)[:120]))

    ok = (len(inlet) > 0 and len(outlet) > 0 and len(walls) > 0 and
          len(per_lo) == len(per_hi) and GetRootPart().Bodies.Count == 1 + len(cavities))
    finish("OK" if ok else "ERROR")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
