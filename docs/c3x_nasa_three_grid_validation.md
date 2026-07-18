# NASA 44344 Three-Grid Validation Decision

## Scope and frozen cases

The three meshes use the same periodic geometry, named boundaries, NASA 44344
mainstream condition, prescribed slice coolant mass flows, SST k-omega model,
constant-air properties, adiabatic vane wall, and area-weighted postprocessing.

| Tier | Cells | Frozen iteration | Whole-wall eta | Protected eta | NASA pressure RMSE | y+ p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coarse CFD | 1,956,019 | 1,800 | 0.57407 | 0.68221 | 0.03519 | 8.38 |
| Paper CFD | 3,776,658 | 2,500 | 0.54953 | 0.64895 | 0.03260 | 2.41 |
| Fine audit | 6,433,128 | 2,000 | 0.49393 | 0.58152 | 0.03802 | 1.11 |

The complete machine-readable table is
`runs/nasa_44344/grid_independence/nasa44344_grid_comparison_final.csv`.

## Convergence decision

- Coarse: iteration 1400 to 1800 changed whole-wall/protected eta by
  `0.076%/0.053%`.
- Paper: iteration 2200 to 2500 changed whole-wall/protected eta by
  `2.03%/2.21%`.
- Fine: iteration 1600 to 2000 changed whole-wall/protected eta by
  `2.60%/2.73%`.

All three meet the frozen provisional thermal plateau gate of at most `3%` over
the final 300-400 iteration checkpoint interval. Earlier iteration-700/750
results are retained only to demonstrate why residual convergence alone was an
insufficient thermal stopping rule.

## Aerodynamic validation decision

The three NASA surface-pressure RMSE values remain in the narrow absolute band
`0.03260-0.03802`. Pressure-side RMSE is `0.00741-0.01002`; suction-side RMSE is
`0.04174-0.04910`. The refinement trend is non-monotonic, which is consistent
with coarse-grid numerical-error cancellation, but no refined mesh shows a
qualitative pressure-loading failure.

Outlet static-pressure means are `170387.54`, `170386.65`, and `170423.03 Pa`
for coarse, paper, and fine, versus the `170416.54 Pa` target. Coolant mass-flow
ratios are unity to numerical precision, and absolute final mass imbalances are
`1.28e-6`, `1.22e-7`, and `1.73e-6 kg/s`.

**Decision:** the current geometry, boundary conditions, and all three meshes
are accepted for the stated aerodynamic baseline and for paired design ranking.
This does not validate every local suction-side pressure point.

## Thermal and mesh-quality decision

Protected eta changes by `-4.88%` from coarse to paper and `-10.39%` from paper
to fine. Whole-wall eta changes by `-4.28%` and `-10.12%`, respectively.
Therefore adiabatic effectiveness is **not grid independent** at the selected
three levels.

For optimization, the information hierarchy is:

- L1 is the frozen one-dimensional film-cooling correlation and row
  superposition knowledge;
- L2 is coarse CFD for low-cost trend and feasibility screening;
- L3 is paper CFD and is the high-fidelity optimization target;
- fine CFD is outside the MFBO loop and audits selected final designs.

The paper mesh is retained as L3 because it combines 3.78M cells, `y+ p95=2.41`,
stable integral eta, and the lowest NASA pressure RMSE. The fine grid gives the
best near-wall resolution but has a lower minimum orthogonal quality and local
temperature-limited cells, so it is not automatically the most accurate model
for every reported quantity.

The paper final interval reached the 1000 K limit in one fluid cell. The fine
final interval reached a maximum of 86 cells at 300 K and 1,393 cells at 1000 K;
the last counts were 75 and 1,313, or about `0.0216%` of fine-grid cells. Fine
vane-wall temperatures were `486.94-886.85 K`, so no wall value was pinned to
the solver bounds. Clipping all local eta values to `[0,1]` changes whole-wall
eta by only `-0.31%`, `-0.52%`, and `-0.31%` relatively for coarse, paper, and
fine. The grids are accepted for integral eta ranking with this limitation, but
not for local temperature/heat-transfer validation near affected cells.

The diagnostic inlet-to-outlet total-pressure difference varies strongly with
mesh and iteration. It is not accepted as a publication constraint until a
normalized loss definition and its grid behavior are frozen.

## Next validation gate

Use the five common designs in
`runs/optimization/nasa_ranking_pilot/controlled_candidates.json` for paired
coarse/paper evaluation. Compute Spearman correlation, four perturbation-sign
checks, top-2 overlap, and paper regret of the best coarse design. Fine-grid
audits are performed only after the L2/L3 optimizer has selected candidates.

## Reproducible outputs

- Final table: `runs/nasa_44344/grid_independence/nasa44344_grid_comparison_final.md`
- Grid metrics: `runs/nasa_44344/grid_independence/nasa44344_grid_metrics_final.png`
- Thermal histories: `runs/nasa_44344/grid_independence/nasa44344_convergence_checkpoints.png`
- Eta clipping audit: `runs/nasa_44344/grid_independence/nasa44344_eta_clipping_audit.json`
- Coarse case/data: `runs/nasa_44344/coarse/*iter1800.{cas,dat}.h5`
- Paper case/data: `runs/nasa_44344/paper/*iter2500.{cas,dat}.h5`
- Fine case/data: `runs/nasa_44344/fine/*iter2000.{cas,dat}.h5`
