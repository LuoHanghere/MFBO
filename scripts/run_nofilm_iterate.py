"""Run iterations for the prepared no-film C3X validation case."""
import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F
from bofm.cfd.nofilm import initialize_and_iterate


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=str(root / "runs" / "fluid" / "c3x_nofilm_setup.cas.h5"))
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--out-prefix", default=str(root / "runs" / "fluid" / "c3x_nofilm_run"))
    ap.add_argument("--cores", type=int, default=4)
    args = ap.parse_args()

    log_path = root / ".cache_nofilm_iterate.txt"
    logf = open(log_path, "w", encoding="utf-8")

    def log(*items):
        msg = " ".join(str(x) for x in items)
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    solver = None
    try:
        case_in = Path(args.case).resolve()
        out_prefix = Path(args.out_prefix).resolve()
        solver = F.launch(mode="solver", processor_count=args.cores, ui_mode="no_gui")
        log("version:", solver.get_fluent_version())
        solver.tui.file.read_case(str(case_in))
        log("read case:", case_in)

        initialize_and_iterate(solver, args.iters)
        log("iterated:", args.iters)

        out_case = out_prefix.with_suffix(".cas.h5")
        out_data = out_prefix.with_suffix(".dat.h5")
        solver.tui.file.write_case(str(out_case))
        solver.tui.file.write_data(str(out_data))
        log("wrote case:", out_case, "exists:", out_case.exists())
        log("wrote data:", out_data, "exists:", out_data.exists())
        log("DONE_OK")
        return 0
    except Exception:
        log("EXCEPTION:\n" + traceback.format_exc())
        return 1
    finally:
        try:
            if solver is not None:
                solver.exit()
        except Exception:
            pass
        logf.close()


if __name__ == "__main__":
    raise SystemExit(main())
