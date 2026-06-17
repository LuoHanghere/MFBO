# SpaceClaim IronPython journal (API V242) -- VANE SOLID (v1).
# Reads BOFM_PLACEMENTS_JSON (embeds profile_xy_mm + span_mm), sketches the
# closed C3X contour, and extrudes it to the full span to make the vane solid.
# Logs each step to BOFM_STATUS for headless diagnosis. Saves to BOFM_OUT_SCDOC.
import os
import json
import traceback

status_path = os.environ.get("BOFM_STATUS")
log = []


def finish(tag):
    if status_path:
        f = open(status_path, "w")
        f.write(tag + "\n" + "\n".join([str(x) for x in log]))
        f.close()


try:
    log.append("started")
    jpath = os.environ.get("BOFM_PLACEMENTS_JSON")
    data = json.load(open(jpath))
    xy = data["profile_xy_mm"]
    span = float(data["span_mm"])
    n = len(xy)
    log.append("loaded %d profile pts, span=%.3f mm" % (n, span))

    # --- sketch the closed contour on the XY plane ---------------------------
    ViewHelper.SetSketchPlane(Plane.PlaneXY)
    log.append("sketch plane set")
    for i in range(n):
        a = xy[i]
        b = xy[(i + 1) % n]
        SketchLine.Create(Point.Create(MM(a[0]), MM(a[1]), MM(0)),
                          Point.Create(MM(b[0]), MM(b[1]), MM(0)))
    log.append("created %d sketch lines" % n)

    # leaving sketch mode fills the closed loop into a planar surface body
    ViewHelper.SetViewMode(InteractionMode.Solid)
    log.append("switched to solid mode")

    bodies = GetRootPart().Bodies
    log.append("bodies after fill: %d" % bodies.Count)
    body = bodies[0]
    faces = body.Faces
    log.append("faces on body[0]: %d" % faces.Count)

    # --- extrude the planar face to the span --------------------------------
    sel = FaceSelection.Create(faces[0])
    options = ExtrudeFaceOptions()
    options.ExtrudeType = ExtrudeType.Add
    ExtrudeFaces.Execute(sel, MM(span), options)
    log.append("extruded to span")

    log.append("final bodies: %d" % GetRootPart().Bodies.Count)

    # --- sanity: bounding box from vertices (SpaceClaim stores SI metres) ----
    try:
        shape = GetRootPart().Bodies[0].Shape
        box = shape.GetBoundingBox(Matrix.Identity)
        mn, mx = box.MinCorner, box.MaxCorner
        bbox = (1000.0 * (mx.X - mn.X),
                1000.0 * (mx.Y - mn.Y),
                1000.0 * (mx.Z - mn.Z))
        log.append("bbox mm (x_axial, y_tang, z_span) = "
                   "%.2f x %.2f x %.2f" % bbox)
    except Exception as be:
        log.append("bbox check skipped: " + str(be))

    out = os.environ.get("BOFM_OUT_SCDOC")
    if out:
        DocumentSave.Execute(out)
        log.append("saved: " + out)

    finish("OK")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
