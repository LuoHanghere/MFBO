"""Create a deterministic, geometry-feasible 8D NASA startup design queue."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import qmc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bofm.optimization.config import load_optimization_config
from bofm.optimization.feasibility import build_geometry_gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="configs/c3x_nasa_standard_mfbo_8d.yaml"
    )
    parser.add_argument(
        "--out", default="configs/c3x_nasa_8d_initial_designs.json"
    )
    parser.add_argument("--per-span-count", type=int, default=3)
    parser.add_argument("--pool-per-count", type=int, default=256)
    args = parser.parse_args()
    if args.per_span_count < 1 or args.pool_per_count < args.per_span_count:
        parser.error("require pool-per-count >= per-span-count >= 1")

    config = load_optimization_config(args.config)
    span = next(spec for spec in config.variables if spec.name == "span_count")
    if span.kind != "integer":
        raise ValueError("span_count must be configured as an integer")
    continuous = tuple(spec for spec in config.variables if spec.name != "span_count")
    gate = build_geometry_gate(
        config.raw.get("optimizer", {}).get("geometry_gate")
    )
    span_counts = list(range(int(span.lower), int(span.upper) + 1))
    selected: dict[int, list[dict[str, float | int]]] = {}
    diagnostics: dict[int, dict[str, int]] = {}

    for count in span_counts:
        sampler = qmc.LatinHypercube(
            d=len(continuous), seed=config.seed + 101 * count
        )
        points = sampler.random(args.pool_per_count)
        accepted: list[dict[str, float | int]] = []
        feasible_count = 0
        for point in points:
            design = {
                spec.name: spec.decode(value)
                for spec, value in zip(continuous, point)
            }
            design["span_count"] = count
            if gate is not None and not gate(design):
                continue
            feasible_count += 1
            encoded = config.encode(design)
            if accepted:
                distance = min(
                    np.linalg.norm(encoded - config.encode(old))
                    for old in accepted
                )
                if distance < 0.22:
                    continue
            accepted.append(design)
            if len(accepted) == args.per_span_count:
                break
        if len(accepted) != args.per_span_count:
            raise RuntimeError(
                f"only found {len(accepted)} startup designs for span_count={count}"
            )
        selected[count] = accepted
        diagnostics[count] = {
            "pool_size": args.pool_per_count,
            "feasible_seen_before_completion": feasible_count,
        }

    records = []
    for replicate in range(args.per_span_count):
        for count in span_counts:
            records.append(
                {
                    "candidate_id": f"N{count}-S{replicate + 1}",
                    "design": selected[count][replicate],
                    "geometry_gate_ok": True,
                }
            )

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": str(Path(args.config).resolve()),
        "seed": config.seed,
        "strategy": "interleaved span-count strata with 7D Latin-hypercube pools",
        "per_span_count": args.per_span_count,
        "span_counts": span_counts,
        "diagnostics": diagnostics,
        "designs": records,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_path = out.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        fields = ["candidate_id", *[spec.name for spec in config.variables]]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({"candidate_id": record["candidate_id"], **record["design"]})
    print(f"wrote {len(records)} designs: {out}")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
