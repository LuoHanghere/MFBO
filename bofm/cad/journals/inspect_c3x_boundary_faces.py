# SpaceClaim IronPython journal (API V242).
# Read-only face inventory used to select stable coolant-plenum inlet targets.
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


def safe_name(obj):
    try:
        return obj.GetName()
    except Exception:
        try:
            return obj.Name
        except Exception:
            return "?"


def bbox_mm(owner):
    bb = owner.Shape.GetBoundingBox(Matrix.Identity)
    mn, mx = bb.MinCorner, bb.MaxCorner
    return [mn.X * 1000.0, mn.Y * 1000.0, mn.Z * 1000.0,
            mx.X * 1000.0, mx.Y * 1000.0, mx.Z * 1000.0]


def area_mm2(face):
    try:
        return float(face.Shape.Area) * 1.0e6
    except Exception:
        box = bbox_mm(face)
        dims = sorted([box[3] - box[0], box[4] - box[1], box[5] - box[2]], reverse=True)
        return dims[0] * dims[1]


try:
    inp = os.environ.get("BOFM_IN_SCDOC")
    out_json = os.environ.get("BOFM_OUT_JSON")
    DocumentOpen.Execute(inp)
    records = []
    for bi in range(GetRootPart().Bodies.Count):
        body = GetRootPart().Bodies[bi]
        faces = []
        for fi in range(body.Faces.Count):
            face = body.Faces[fi]
            box = bbox_mm(face)
            faces.append({
                "index": fi,
                "bbox_mm": box,
                "center_mm": [(box[0] + box[3]) * 0.5,
                              (box[1] + box[4]) * 0.5,
                              (box[2] + box[5]) * 0.5],
                "size_mm": [box[3] - box[0], box[4] - box[1], box[5] - box[2]],
                "area_mm2": area_mm2(face),
            })
        records.append({
            "body_index": bi,
            "body_name": safe_name(body),
            "body_bbox_mm": bbox_mm(body),
            "face_count": int(body.Faces.Count),
            "faces": faces,
        })
        log.append("body %d %s faces=%d" % (bi, safe_name(body), body.Faces.Count))
    data = {"source_scdoc": inp, "units": "mm", "bodies": records}
    f = open(out_json, "w")
    f.write(json.dumps(data, indent=2))
    f.close()
    log.append("wrote: " + out_json)
    finish("OK")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
