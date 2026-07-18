# SpaceClaim IronPython journal (API V242).
# Add variable downstream cylinders to the fixed-LE template and unite all
# connected coolant/mainstream volumes into one CFD fluid body.
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


def point(values):
    return Point.Create(MM(float(values[0])), MM(float(values[1])), MM(float(values[2])))


def bodies():
    return [GetRootPart().Bodies[i] for i in range(GetRootPart().Bodies.Count)]


def find_body(names):
    for body in bodies():
        if safe_name(body) in names:
            return body
    return None


def bbox_center_mm(owner):
    bb = owner.Shape.GetBoundingBox(Matrix.Identity)
    mn, mx = bb.MinCorner, bb.MaxCorner
    return [0.5 * (mn.X + mx.X) * 1000.0,
            0.5 * (mn.Y + mx.Y) * 1000.0,
            0.5 * (mn.Z + mx.Z) * 1000.0]


def bbox_mm(owner):
    bb = owner.Shape.GetBoundingBox(Matrix.Identity)
    mn, mx = bb.MinCorner, bb.MaxCorner
    return [mn.X * 1000.0, mn.Y * 1000.0, mn.Z * 1000.0,
            mx.X * 1000.0, mx.Y * 1000.0, mx.Z * 1000.0]


def distance(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def add_cylinder(marker):
    start = [float(x) for x in marker["start_mm"]]
    end = [float(x) for x in marker["end_mm"]]
    radius = float(marker["radius_mm"])
    rv = marker.get("radius_vector_mm", [0.0, 0.0, radius])
    radius_point = [end[i] + float(rv[i]) for i in range(3)]
    CylinderBody.Create(point(start), point(end), point(radius_point),
                        ExtrudeType.ForceIndependent, None)
    body = GetRootPart().Bodies[GetRootPart().Bodies.Count - 1]
    rename_obj(body, "variable_hole_" + marker["id"])
    if body.Faces.Count != 3:
        raise ValueError("non-cylindrical marker " + marker["id"])
    return body


def unite_into(target, tool, label):
    before = GetRootPart().Bodies.Count
    try:
        target.Shape.Unite(tool.Shape)
        try:
            Delete.Execute(BodySelection.Create([tool]))
        except Exception:
            pass
        reduced = GetRootPart().Bodies.Count == before - 1
        log.append("unite %s reduced=%s bodies=%d faces=%d" % (
            label, reduced, GetRootPart().Bodies.Count, target.Faces.Count
        ))
        return reduced
    except Exception as exc:
        log.append("unite %s FAILED: %s" % (label, str(exc)[:180]))
        return False


def name_faces(group_name, face_list):
    if len(face_list) < 1:
        log.append("named %s skipped empty" % group_name)
        return None
    result = NamedSelection.Create(FaceSelection.Create(face_list), Selection.Empty())
    rename_obj(result.CreatedNamedSelection, group_name)
    log.append("named %s faces=%d" % (group_name, len(face_list)))
    return result.CreatedNamedSelection


def find_target_face_index(group_name, target, tolerance, body):
    best = None
    best_index = None
    best_distance = 1.0e99
    for fi in range(body.Faces.Count):
        face = body.Faces[fi]
        d = distance(bbox_center_mm(face), target)
        if d < best_distance:
            best = face
            best_index = fi
            best_distance = d
    if best is None or best_distance > tolerance:
        raise ValueError("boundary target miss %s distance=%.6f" % (group_name, best_distance))
    log.append("target %s face=%d distance_mm=%.9f" % (group_name, best_index, best_distance))
    return best_index


def classify_boundary_faces(body, passage, span_mm, diameter_mm, target_specs):
    eps = 0.5
    x_in = float(passage["x_in"])
    x_out = float(passage["x_out"])
    pitch = float(passage.get("periodic_width_mm", passage.get("pitch_mm")))
    physical_pitch = float(passage.get("physical_pitch_mm", pitch))
    pitch_candidates = [pitch]
    if abs(physical_pitch - pitch) > 1.0e-9:
        pitch_candidates.append(physical_pitch)
    y_low = passage.get("y_low")
    y_high = passage.get("y_high")
    if y_low is not None:
        y_low = float(y_low)
    if y_high is not None:
        y_high = float(y_high)
    axial = x_out - x_in
    groups = {
        "inlet": [],
        "outlet": [],
        "span_low": [],
        "span_high": [],
        "periodic_low": [],
        "periodic_high": [],
        "vane_wall": [],
        "film_hole_wall": [],
    }
    target_indices = {}
    claimed = set()
    for group_name, spec in target_specs["boundaries"].items():
        idx = find_target_face_index(group_name, spec["center_mm"],
                                     float(spec["cad_tolerance_mm"]), body)
        target_indices[group_name] = idx
        claimed.add(idx)

    periodic = []
    for fi in range(body.Faces.Count):
        if fi in claimed:
            continue
        face = body.Faces[fi]
        bb = bbox_mm(face)
        x0, y0, z0, x1, y1, z1 = bb
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        cx, cy, cz = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)
        if 0.75 * diameter_mm <= dz <= 1.25 * diameter_mm and max(dx, dy) >= 1.5 * diameter_mm:
            groups["film_hole_wall"].append(fi)
        elif dz < eps:
            groups["span_low" if cz < span_mm * 0.5 else "span_high"].append(fi)
        elif y_low is not None and dy < eps and dx > 0.5 * axial and abs(cy - y_low) < eps:
            groups["periodic_low"].append(fi)
        elif y_high is not None and dy < eps and dx > 0.5 * axial and abs(cy - y_high) < eps:
            groups["periodic_high"].append(fi)
        elif dx < eps and abs(cx - x_in) < eps:
            groups["inlet"].append(fi)
        elif dx < eps and abs(cx - x_out) < eps:
            groups["outlet"].append(fi)
        else:
            touches_in = abs(x0 - x_in) < eps or abs(x1 - x_in) < eps
            touches_out = abs(x0 - x_out) < eps or abs(x1 - x_out) < eps
            if touches_in and touches_out:
                groups["vane_wall"].append(fi)
            elif touches_in or touches_out:
                periodic.append((fi, cx, cy))
            else:
                groups["vane_wall"].append(fi)

    used = set()
    for i in range(len(periodic)):
        if i in used:
            continue
        fi, cx, cy = periodic[i]
        match = None
        is_low = True
        for j in range(len(periodic)):
            if i == j or j in used:
                continue
            fj, cxj, cyj = periodic[j]
            for pitch_i in pitch_candidates:
                if abs(cxj - cx) < eps and abs((cy + pitch_i) - cyj) < 3.0:
                    match, is_low = j, True
                    break
                if abs(cxj - cx) < eps and abs((cy - pitch_i) - cyj) < 3.0:
                    match, is_low = j, False
                    break
            if match is not None:
                break
        if match is None:
            groups["vane_wall"].append(fi)
            used.add(i)
        else:
            fj = periodic[match][0]
            if is_low:
                groups["periodic_low"].append(fi)
                groups["periodic_high"].append(fj)
            else:
                groups["periodic_low"].append(fj)
                groups["periodic_high"].append(fi)
            used.add(i)
            used.add(match)

    for name, idx in target_indices.items():
        groups[name] = [idx]
    return groups


def boundary_style():
    style = (os.environ.get("BOFM_BOUNDARY_STYLE") or "cfd").strip().lower()
    if style not in ("cfd", "workbench"):
        raise ValueError("BOFM_BOUNDARY_STYLE must be 'cfd' or 'workbench'")
    return style


def coolant_face_names(style):
    if style == "workbench":
        return {
            "coolant_inlet_LE": "qian",
            "coolant_inlet_SS": "ss",
            "coolant_inlet_PS": "ps",
        }
    return {
        "coolant_inlet_LE": "coolant_inlet_LE",
        "coolant_inlet_SS": "coolant_inlet_SS",
        "coolant_inlet_PS": "coolant_inlet_PS",
    }


def fluid_body_name(style):
    return "fixed_fluid_domain" if style == "workbench" else "fluid"


def create_boundary_named_selections(body, passage, layout, targets):
    span_mm = float(layout["geometry"]["periodic_span_mm"])
    diameter_mm = float(layout["geometry"]["diameter_mm"])
    groups = classify_boundary_faces(body, passage, span_mm, diameter_mm, targets)
    faces = [body.Faces[i] for i in range(body.Faces.Count)]
    style = boundary_style()
    coolant = coolant_face_names(style)
    for name in [
        "inlet", "outlet", "span_low", "span_high",
        "periodic_low", "periodic_high", "vane_wall", "film_hole_wall",
    ]:
        name_faces(name, [faces[i] for i in groups.get(name, [])])
    for internal, export_name in coolant.items():
        name_faces(export_name, [faces[i] for i in groups.get(internal, [])])
    log.append("boundary style=%s" % style)


def save_outputs(path):
    DocumentSave.Execute(path)
    log.append("saved: " + path)
    # Route B (Workbench): import SCDOC in Discovery only — SAT loses face labels.
    if (os.environ.get("BOFM_EXPORT_SAT") or "0").strip().lower() in ("1", "true", "yes"):
        base = path[:-6] if path.lower().endswith(".scdoc") else path
        for ext in (".sat", ".fmd"):
            try:
                DocumentSave.Execute(base + ext)
                log.append("exported: " + base + ext)
            except Exception as exc:
                log.append("export %s failed: %s" % (ext, str(exc)[:160]))
    else:
        log.append("skipped SAT/FMD export (Workbench Route B: use SCDOC in Discovery)")


try:
    inp = os.environ.get("BOFM_IN_SCDOC")
    out = os.environ.get("BOFM_OUT_SCDOC")
    layout = json.load(open(os.environ.get("BOFM_DOWNSTREAM_LAYOUT_JSON")))
    targets = json.load(open(os.environ.get("BOFM_BOUNDARY_TARGETS_JSON")))
    passage = json.load(open(os.environ.get("BOFM_PASSAGE_JSON")))
    DocumentOpen.Execute(inp)
    main = find_body(["fluid_fixed_LE"])
    ss_plenum = find_body(["SS_plenum", "SS"])
    ps_plenum = find_body(["PS_plenum", "PS"])
    if main is None or ss_plenum is None or ps_plenum is None:
        raise ValueError("fixed-LE template must contain fluid_fixed_LE, SS_plenum, PS_plenum")
    if GetRootPart().Bodies.Count != 3:
        raise ValueError("fixed-LE template must start with exactly three bodies")

    hole_bodies = []
    for row in layout["rows"]:
        for marker in row["cylinder_markers"]:
            hole_bodies.append((marker["id"], add_cylinder(marker)))
    span_count = int(layout["geometry"]["span_count_per_row"])
    expected_holes = len(layout["rows"]) * span_count
    if len(hole_bodies) != expected_holes:
        raise ValueError(
            "expected %d downstream cylinders for span_count=%d, got %d"
            % (expected_holes, span_count, len(hole_bodies))
        )
    log.append("created downstream cylinders=%d" % len(hole_bodies))

    merged_ok = True
    for label, hole in hole_bodies:
        merged_ok = unite_into(main, hole, label) and merged_ok
    merged_ok = unite_into(main, ss_plenum, "SS_plenum") and merged_ok
    merged_ok = unite_into(main, ps_plenum, "PS_plenum") and merged_ok
    style = boundary_style()
    out_body = fluid_body_name(style)
    rename_obj(main, out_body)

    create_boundary_named_selections(main, passage, layout, targets)

    final_ok = merged_ok and GetRootPart().Bodies.Count == 1 and safe_name(main) == out_body
    log.append("final bodies=%d faces=%d" % (GetRootPart().Bodies.Count, main.Faces.Count))
    save_outputs(out)
    finish("OK" if final_ok else "ERROR")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
