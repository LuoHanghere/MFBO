# SpaceClaim IronPython journal (API V242).
# Create named selections for the three fixed coolant-supply faces.
import json
import math
import os
import traceback


status_path = os.environ.get("BOFM_STATUS")
log = []


def finish(tag):
    if status_path:
        f = open(status_path, "w")
        f.write(tag + "\n" + "\n".join([str(x) for x in log]))
        f.close()


def safe_name(obj):
    try:
        return obj.GetName()
    except Exception:
        try:
            return obj.Name
        except Exception:
            return "?"


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


def bbox_center_mm(owner):
    bb = owner.Shape.GetBoundingBox(Matrix.Identity)
    mn, mx = bb.MinCorner, bb.MaxCorner
    return [0.5 * (mn.X + mx.X) * 1000.0,
            0.5 * (mn.Y + mx.Y) * 1000.0,
            0.5 * (mn.Z + mx.Z) * 1000.0]


def distance(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def find_body(names):
    for i in range(GetRootPart().Bodies.Count):
        body = GetRootPart().Bodies[i]
        if safe_name(body) in names:
            return body
    return None


def create_face_group(name, face):
    result = NamedSelection.Create(FaceSelection.Create([face]), Selection.Empty())
    rename_obj(result.CreatedNamedSelection, name)


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
    targets = json.load(open(os.environ.get("BOFM_BOUNDARY_TARGETS_JSON")))
    DocumentOpen.Execute(inp)
    selected = []
    for name, spec in targets["boundaries"].items():
        body = find_body(spec["body_names"])
        if body is None:
            raise ValueError("body not found for " + name)
        target = spec["center_mm"]
        best = None
        best_distance = 1.0e99
        for fi in range(body.Faces.Count):
            face = body.Faces[fi]
            d = distance(bbox_center_mm(face), target)
            if d < best_distance:
                best = face
                best_distance = d
        if best is None or best_distance > float(spec["cad_tolerance_mm"]):
            raise ValueError("face target miss for %s: distance %.6f mm" % (name, best_distance))
        create_face_group(name, best)
        selected.append(name)
        log.append("named %s body=%s distance_mm=%.9f" % (
            name, safe_name(body), best_distance
        ))
    save_outputs(out)
    finish("OK" if len(selected) == 3 else "ERROR")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
