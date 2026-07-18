# SpaceClaim IronPython journal (API V242).
# Freeze the user-built leading-edge plenum and the ten LE cylinders into the
# main fluid body. SS/PS plenums remain independent; downstream cylinders are
# either retained for review or removed for the clean parameterization base.
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


def bodies():
    return [GetRootPart().Bodies[i] for i in range(GetRootPart().Bodies.Count)]


def find_exact(name):
    for body in bodies():
        if safe_name(body) == name:
            return body
    return None


def find_prefix(prefix):
    return [body for body in bodies() if safe_name(body).startswith(prefix)]


def delete_bodies(items, label):
    if not items:
        return
    Delete.Execute(BodySelection.Create(items))
    log.append("deleted %s: %d" % (label, len(items)))


def unite_into(target, tool, label):
    before = GetRootPart().Bodies.Count
    try:
        target.Shape.Unite(tool.Shape)
        try:
            Delete.Execute(BodySelection.Create([tool]))
        except Exception:
            pass
        reduced = GetRootPart().Bodies.Count == before - 1
        log.append("unite %s: reduced=%s bodies=%d target_faces=%d" % (
            label, reduced, GetRootPart().Bodies.Count, target.Faces.Count
        ))
        return reduced
    except Exception as exc:
        log.append("unite %s FAILED: %s" % (label, str(exc)[:180]))
        return False


def make_body_group(name, items):
    if not items:
        return
    try:
        result = NamedSelection.Create(BodySelection.Create(items), Selection.Empty())
        rename_obj(result.CreatedNamedSelection, name)
        log.append("group %s bodies=%d" % (name, len(items)))
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
    keep_downstream = os.environ.get("BOFM_KEEP_DOWNSTREAM", "1") != "0"
    log.append("open: " + inp)
    log.append("keep_downstream: %s" % keep_downstream)
    DocumentOpen.Execute(inp)

    main = find_exact("fluid")
    le_plenum = find_exact("For") or find_exact("LE_plenum")
    ss_plenum = find_exact("SS") or find_exact("SS_plenum")
    ps_plenum = find_exact("PS") or find_exact("PS_plenum")
    le_holes = find_prefix("paper_hole_LE")
    downstream = find_prefix("paper_hole_SS") + find_prefix("paper_hole_PS")
    log.append("found main=%s LE_plenum=%s SS=%s PS=%s LE_holes=%d downstream=%d" % (
        main is not None, le_plenum is not None, ss_plenum is not None,
        ps_plenum is not None, len(le_holes), len(downstream)
    ))
    if main is None or le_plenum is None or ss_plenum is None or ps_plenum is None:
        raise ValueError("required fluid/plenum body is missing")
    if len(le_holes) != 10 or len(downstream) != 20:
        raise ValueError("expected 10 LE and 20 downstream cylinders")

    if not keep_downstream:
        delete_bodies(downstream, "downstream marker cylinders")
        downstream = []

    merged_ok = True
    for hole in list(le_holes):
        merged_ok = unite_into(main, hole, safe_name(hole)) and merged_ok
    merged_ok = unite_into(main, le_plenum, "LE_plenum") and merged_ok

    rename_obj(main, "fluid_fixed_LE")
    rename_obj(ss_plenum, "SS_plenum")
    rename_obj(ps_plenum, "PS_plenum")
    if keep_downstream:
        make_body_group("variable_downstream_hole_markers", downstream)
    make_body_group("fixed_fluid_domain", [main])
    make_body_group("downstream_plenums", [ss_plenum, ps_plenum])

    remaining_le = find_prefix("paper_hole_LE")
    remaining_downstream = find_prefix("paper_hole_SS") + find_prefix("paper_hole_PS")
    expected_count = 23 if keep_downstream else 3
    names = [safe_name(body) for body in bodies()]
    log.append("final bodies=%d names=%s" % (GetRootPart().Bodies.Count, names))
    ok = (
        merged_ok
        and GetRootPart().Bodies.Count == expected_count
        and len(remaining_le) == 0
        and len(remaining_downstream) == (20 if keep_downstream else 0)
        and safe_name(main) == "fluid_fixed_LE"
        and main.Faces.Count > 964
    )
    save_outputs(out)
    finish("OK" if ok else "ERROR")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
