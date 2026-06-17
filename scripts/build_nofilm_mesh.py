"""Build a no-film C3X Fluent mesh/case from the current SAT fluid domain."""
import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bofm.cfd.fluent as F
from bofm.cfd.mesh import DomainBounds, build_watertight_mesh

TIERS = {
    "coarse": {
        "surface": {"MinSize": 0.2, "MaxSize": 4.0, "GrowthRate": 1.2},
        "n_prism": 8,
        "volume_fill": "poly-hexcore",
    },
    "refined": {
        "surface": {"MinSize": 0.15, "MaxSize": 3.0, "GrowthRate": 1.18},
        "n_prism": 10,
        "volume_fill": "poly-hexcore",
    },
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=TIERS, default="coarse")
    ap.add_argument("--sat", default=str(root / "runs" / "fluid" / "c3x_fluid_nofilm.sat"))
    ap.add_argument("--passage", default=str(root / "configs" / "c3x_passage.json"))
    ap.add_argument("--out-prefix", default=None)
    ap.add_argument("--cores", type=int, default=4)
    args = ap.parse_args()

    tier = TIERS[args.tier]
    out_prefix = Path(args.out_prefix) if args.out_prefix else \
        root / "runs" / "fluid" / f"c3x_nofilm_{args.tier}"
    out_msh = out_prefix.with_suffix(".msh.h5")
    out_case = out_prefix.with_suffix(".cas.h5")
    log_path = root / f".cache_nofilm_mesh_{args.tier}.txt"
    logf = open(log_path, "w", encoding="utf-8")

    def log(*items):
        msg = " ".join(str(x) for x in items)
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    session = None
    try:
        bounds = DomainBounds.from_passage_json(args.passage, span_mm=3.96)
        session = F.launch(mode="meshing", processor_count=args.cores, ui_mode="no_gui")
        log("version:", session.get_fluent_version())
        groups = build_watertight_mesh(
            session,
            Path(args.sat).resolve(),
            bounds,
            out_msh=out_msh.resolve(),
            n_prism=tier["n_prism"],
            volume_fill=tier["volume_fill"],
            surface_controls=tier["surface"],
        )
        log("tagged groups:", {k: len(v) for k, v in groups.items()})
        log("wrote mesh:", out_msh, "exists:", out_msh.exists())
        session.tui.switch_to_solution_mode("yes")
        session.tui.file.write_case(str(out_case.resolve()))
        log("wrote case:", out_case, "exists:", out_case.exists())
        log("DONE_OK")
        return 0
    except Exception:
        log("EXCEPTION:\n" + traceback.format_exc())
        return 1
    finally:
        try:
            if session is not None:
                session.exit()
        except Exception:
            pass
        logf.close()


if __name__ == "__main__":
    raise SystemExit(main())
