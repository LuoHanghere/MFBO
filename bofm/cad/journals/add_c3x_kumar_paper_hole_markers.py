# SpaceClaim IronPython journal (API V242).
# Add independent pure-cylinder marker bodies to the Kumar/NASA C3X flow base.
import json
import os
import traceback


status_path = os.environ.get("BOFM_STATUS")
log = []


def finish(tag):
    if status_path:
        f = open(status_path, "w")
        f.write(tag + "\n" + "\n".join([str(x) for x in log]))
        f.close()


def pt(values):
    return Point.Create(MM(float(values[0])), MM(float(values[1])), MM(float(values[2])))


def rename_obj(obj, name):
    try:
        RenameObject.Execute(Selection.Create(obj), name)
        return
    except Exception:
        pass
    try:
        obj.SetName(name)
    except Exception:
        pass


def add_cylinder(row, marker):
    start = [float(x) for x in marker["start_mm"]]
    end = [float(x) for x in marker["end_mm"]]
    radius = float(marker["radius_mm"])
    radius_vector = marker.get("radius_vector_mm", [0.0, 0.0, radius])
    radius_point_at_end = [
        end[0] + float(radius_vector[0]),
        end[1] + float(radius_vector[1]),
        end[2] + float(radius_vector[2]),
    ]
    CylinderBody.Create(
        pt(start),
        pt(end),
        pt(radius_point_at_end),
        ExtrudeType.ForceIndependent,
        None,
    )
    body = GetRootPart().Bodies[GetRootPart().Bodies.Count - 1]
    name = "paper_hole_" + marker["id"]
    rename_obj(body, name)
    log.append("created %s faces=%d" % (name, body.Faces.Count))
    return body


def make_body_group(name, bodies):
    if not bodies:
        return
    try:
        result = NamedSelection.Create(BodySelection.Create(bodies), Selection.Empty())
        rename_obj(result.CreatedNamedSelection, name)
        log.append("group %s bodies=%d" % (name, len(bodies)))
    except Exception as exc:
        log.append("group %s failed: %s" % (name, str(exc)[:160]))


def save_outputs(path):
    DocumentSave.Execute(path)
    log.append("saved: " + path)
    base = path[:-6] if path.lower().endswith(".scdoc") else path
    for ext in (".sat", ".fmd"):
        try:
            DocumentSave.Execute(base + ext)
            log.append("exported: " + base + ext)
        except Exception as exc:
            log.append("export %s failed: %s" % (ext, str(exc)[:160]))


try:
    inp = os.environ.get("BOFM_IN_SCDOC")
    out = os.environ.get("BOFM_OUT_SCDOC")
    layout_path = os.environ.get("BOFM_KUMAR_LAYOUT_JSON")
    layout = json.load(open(layout_path))
    rows = layout.get("rows", [])
    leading_edge_rows = layout.get("leading_edge_rows", [])
    log.append("open: " + inp)
    log.append("layout: %s downstream_rows=%d leading_edge_rows=%d" % (
        layout_path, len(rows), len(leading_edge_rows)
    ))
    DocumentOpen.Execute(inp)
    if GetRootPart().Bodies.Count:
        rename_obj(GetRootPart().Bodies[0], "fluid")

    downstream_bodies = []
    for row in rows:
        for marker in row.get("cylinder_markers", []):
            downstream_bodies.append(add_cylinder(row, marker))
    leading_edge_bodies = []
    for row in leading_edge_rows:
        for marker in row.get("cylinder_markers", []):
            leading_edge_bodies.append(add_cylinder(row, marker))
    make_body_group("paper_downstream_hole_markers", downstream_bodies)
    make_body_group("paper_le_hole_markers", leading_edge_bodies)
    save_outputs(out)
    bodies = downstream_bodies + leading_edge_bodies
    ok = (
        len(downstream_bodies) == 20
        and len(leading_edge_bodies) == 10
        and all(body.Faces.Count == 3 for body in bodies)
    )
    finish("OK" if ok else "ERROR")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
