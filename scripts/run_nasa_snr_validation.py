"""Run the paired fluid-only NASA 44344 FC/NFC SNR workflow."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("RUN:", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restart-case", required=True)
    parser.add_argument("--restart-data", required=True)
    parser.add_argument(
        "--out-root",
        default=str(ROOT / "runs" / "nasa_44344" / "snr_validation" / "coarse"),
    )
    parser.add_argument("--fc-iters", type=int, default=250)
    parser.add_argument("--nfc-iters", type=int, default=300)
    parser.add_argument("--cores", type=int, default=16)
    parser.add_argument("--precision", choices=("single", "double"), default="single")
    parser.add_argument("--fc-transcript")
    parser.add_argument("--nfc-transcript")
    parser.add_argument("--skip-solve", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    args = parser.parse_args()

    out_root = Path(args.out_root).resolve()
    fc_prefix = out_root / "fc" / f"nasa44344_snr_fc_iter{args.fc_iters}"
    nfc_prefix = out_root / "nfc" / f"nasa44344_snr_nfc_iter{args.nfc_iters}"
    fc_post = out_root / "fc" / "post"
    nfc_post = out_root / "nfc" / "post"
    comparison = out_root / "comparison"

    if not args.skip_solve:
        run([
            sys.executable, "scripts/run_workbench_film_continue.py",
            "--case", str(Path(args.restart_case).resolve()),
            "--data", str(Path(args.restart_data).resolve()),
            "--additional-iters", str(args.fc_iters),
            "--out-prefix", str(fc_prefix),
            "--cores", str(args.cores),
            "--precision", args.precision,
            "--energy-urf", "0.5",
            "--temperature-min-k", "300",
            "--temperature-max-k", "1000",
            "--reapply-outer-bcs",
            "--simulation-case", "nasa_44344_snr_fc",
        ])
        run([
            sys.executable, "scripts/run_workbench_film_continue.py",
            "--case", str(fc_prefix.with_suffix(".cas.h5")),
            "--data", str(fc_prefix.with_suffix(".dat.h5")),
            "--additional-iters", str(args.nfc_iters),
            "--out-prefix", str(nfc_prefix),
            "--cores", str(args.cores),
            "--precision", args.precision,
            "--energy-urf", "0.5",
            "--momentum-urf", "0.4",
            "--turbulence-urf", "0.35",
            "--temperature-min-k", "300",
            "--temperature-max-k", "1000",
            "--reapply-outer-bcs",
            "--simulation-case", "nasa_44344_snr_nfc",
        ])

    if not args.skip_export:
        for prefix, post, case_name, transcript in (
            (fc_prefix, fc_post, "nasa_44344_snr_fc", args.fc_transcript),
            (nfc_prefix, nfc_post, "nasa_44344_snr_nfc", args.nfc_transcript),
        ):
            command = [
                sys.executable, "scripts/export_workbench_film_results.py",
                "--case", str(prefix.with_suffix(".cas.h5")),
                "--data", str(prefix.with_suffix(".dat.h5")),
                "--out-dir", str(post),
                "--simulation-case", case_name,
                "--cores", "4",
                "--precision", args.precision,
            ]
            if transcript:
                command.extend(["--log", str(Path(transcript).resolve())])
            run(command)

    run([
        sys.executable, "scripts/compare_nasa_snr.py",
        "--fc-post", str(fc_post),
        "--nfc-post", str(nfc_post),
        "--out-dir", str(comparison),
    ])
    print("SNR summary:", comparison / "snr_validation_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
