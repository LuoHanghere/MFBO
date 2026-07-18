# SpaceClaim IronPython journal (API V242) -- OPEN AND EXPORT EXISTING SCDOC.
import os
import traceback

status_path = os.environ.get("BOFM_STATUS")
log = []


def finish(tag):
    if status_path:
        f = open(status_path, "w")
        f.write(tag + "\n" + "\n".join([str(x) for x in log]))
        f.close()


try:
    inp = os.environ.get("BOFM_IN_SCDOC")
    out = os.environ.get("BOFM_OUT_SCDOC")
    log.append("open: " + inp)
    DocumentOpen.Execute(inp)
    if out:
        DocumentSave.Execute(out)
        log.append("saved: " + out)
        base = out[:-6] if out.endswith(".scdoc") else out
        for ext in [".sat", ".fmd"]:
            try:
                DocumentSave.Execute(base + ext)
                log.append("export " + ext)
            except Exception as e:
                log.append("export " + ext + " failed: " + str(e)[:140])
    finish("OK")
except Exception:
    log.append(traceback.format_exc())
    finish("ERROR")
