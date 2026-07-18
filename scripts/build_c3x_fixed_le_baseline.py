"""Build fixed-leading-edge review and downstream-parameterization SCDOCs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal


ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "bofm" / "cad" / "journals" / "merge_c3x_fixed_le_baseline.py"


def run_variant(source: Path, output: Path, keep_downstream: bool) -> bool:
    result = run_journal(
        JOURNAL,
        out_scdoc=output,
        env_extra={
            "BOFM_IN_SCDOC": str(source),
            "BOFM_KEEP_DOWNSTREAM": "1" if keep_downstream else "0",
        },
        headless=True,
        timeout_s=900,
    )
    print(result.status)
    return result.ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in-scdoc",
        default=str(ROOT / "runs" / "fluid" / "c3x_kumar_case1_hole_markers_unmerged.scdoc"),
    )
    parser.add_argument(
        "--review-scdoc",
        default=str(ROOT / "runs" / "fluid" / "c3x_kumar_case1_fixed_le_review.scdoc"),
    )
    parser.add_argument(
        "--template-scdoc",
        default=str(ROOT / "runs" / "fluid" / "c3x_kumar_fixed_le_template.scdoc"),
    )
    args = parser.parse_args()

    source = Path(args.in_scdoc).resolve()
    review = Path(args.review_scdoc).resolve()
    template = Path(args.template_scdoc).resolve()
    review.parent.mkdir(parents=True, exist_ok=True)
    template.parent.mkdir(parents=True, exist_ok=True)

    print("building fixed-LE review model ...", flush=True)
    review_ok = run_variant(source, review, keep_downstream=True)
    print("building clean downstream-parameterization template ...", flush=True)
    template_ok = run_variant(source, template, keep_downstream=False)
    print("review:", review)
    print("template:", template)
    return 0 if review_ok and template_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
