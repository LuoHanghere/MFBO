# SpaceClaim IronPython journal (API V242) -- FLUID DOMAIN (no-film).
# Reads BOFM_PASSAGE_JSON (single-pitch periodic passage loop, pitch, x_in/x_out)
# + BOFM_SPAN_MM (thin slice for no-film / one hole pitch for film). Sketches the
# passage outline, extrudes to span, then classifies the resulting faces by
# position and creates named selections (inlet/outlet/periodic_low/periodic_high/
# span_low/span_high/walls) so Fluent Meshing can apply BCs. Saves BOFM_OUT_SCDOC.
import os
import json
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
    x0, y0, z0 = mn.X * 1000, mn.Y * 1000, mn.Z * 1000
    x1, y1, z1 = mx.X * 1000, mx.Y * 1000, mx.Z * 1000
    return (x0, y0, z0, x1, y1, z1)


def make_ns(name, faces):
    if not faces:
        log.append("NS %s: SKIP (0 faces)" % name)
        return
    sel = FaceSelection.Create(faces)
    res = NamedSelection.Create(sel, Selection.Empty())
    grp = res.CreatedNamedSelection
    renamed = "?"
    try:
        RenameObject.Execute(Selection.Create(grp), name)
        renamed = "rename"
    except Exception:
        try:
            grp.SetName(name)
            renamed = "SetName"
        except Exception as e2:
            renamed = "FAILED:" + str(e2)
    log.append("NS %s: %d faces (%s)" % (name, len(faces), renamed))


try:
    log.append("started")
    data = json.load(open(os.environ.get("BOFM_PASSAGE_JSON")))
    loop = data["loop_xy_mm"]
    x_in = float(data["x_in"])
    x_out = float(data["x_out"])
    pitch = float(data["pitch_mm"])
    span_env = os.environ.get("BOFM_SPAN_MM")
    span = float(span_env) if span_env else float(data["span_mm"])
    n = len(loop)
    log.append("loaded %d loop pts, span=%.3f, pitch=%.2f, x_in=%.1f, x_out=%.1f"
               % (n, span, pitch, x_in, x_out))

    ViewHelper.SetSketchPlane(Plane.PlaneXY)
    for i in range(n):
        a = loop[i]
        b = loop[(i + 1) % n]
        SketchLine.Create(Point.Create(MM(a[0]), MM(a[1]), MM(0)),
                          Point.Create(MM(b[0]), MM(b[1]), MM(0)))
    ViewHelper.SetViewMode(InteractionMode.Solid)
    body = GetRootPart().Bodies[0]
    log.append("filled: bodies=%d faces=%d" %
               (GetRootPart().Bodies.Count, body.Faces.Count))

    sel = FaceSelection.Create(body.Faces[0])
    options = ExtrudeFaceOptions()
    options.ExtrudeType = ExtrudeType.Add
    ExtrudeFaces.Execute(sel, MM(span), options)
    body = GetRootPart().Bodies[0]
    log.append("extruded: faces=%d" % body.Faces.Count)

    # --- classify faces by bounding box -------------------------------------
    inlet, outlet, span_lo, span_hi, walls = [], [], [], [], []
    periodic = []  # (face, cx, cy)
    for idx in range(body.Faces.Count):
        f = body.Faces[idx]
        x0, y0, z0, x1, y1, z1 = bbox_mm(f)
        cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
        dx, dz = x1 - x0, z1 - z0
        if dz < EPS:                                   # z-plane -> span cap
            (span_lo if cz < span * 0.5 else span_hi).append(f)
        elif dx < EPS and abs(cx - x_in) < EPS:
            inlet.append(f)
        elif dx < EPS and abs(cx - x_out) < EPS:
            outlet.append(f)
        elif abs(x0 - x_in) < EPS or abs(x1 - x_out) < EPS:
            periodic.append((f, cx, cy))               # extension faces
        else:
            walls.append(f)                            # blade surfaces

    # pair periodic faces by +pitch in y -> low/high
    per_lo, per_hi = [], []
    used = set()
    for i in range(len(periodic)):
        if i in used:
            continue
        fi, cxi, cyi = periodic[i]
        m = None
        is_low = True
        for j in range(len(periodic)):
            if j == i or j in used:
                continue
            fj, cxj, cyj = periodic[j]
            if abs(cxj - cxi) < EPS and abs((cyi + pitch) - cyj) < 3.0:
                m, is_low = j, True       # partner is above -> self is low
                break
            if abs(cxj - cxi) < EPS and abs((cyi - pitch) - cyj) < 3.0:
                m, is_low = j, False      # partner is below -> self is high
                break
        if m is not None:
            if is_low:
                per_lo.append(fi)
                per_hi.append(periodic[m][0])
            else:
                per_hi.append(fi)
                per_lo.append(periodic[m][0])
            used.add(i)
            used.add(m)
        else:
            per_lo.append(fi)   # unpaired fallback (should not happen)
            used.add(i)
    log.append("classified: inlet=%d outlet=%d span_lo=%d span_hi=%d "
               "periodic=%d (lo=%d,hi=%d) walls=%d" %
               (len(inlet), len(outlet), len(span_lo), len(span_hi),
                len(periodic), len(per_lo), len(per_hi), len(walls)))

    # --- create named selections --------------------------------------------
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
        # also export neutral meshing formats: the native .scdoc PartMgr reader
        # fails headlessly. Only .sat (ACIS solid) and .fmd write in batch mode.
        base = out[:-6] if out.endswith(".scdoc") else out
        for ext in (".sat", ".fmd"):
            try:
                DocumentSave.Execute(base + ext)
                ok = os.path.exists(base + ext)
                log.append("exported %s -> exists=%s" % (ext, ok))
            except Exception as ee:
                log.append("export %s FAILED: %s" % (ext, str(ee)[:140]))

    finish("OK")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
