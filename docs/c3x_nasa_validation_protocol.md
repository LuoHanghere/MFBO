# C3X NASA validation and BO evaluation protocol

This protocol fixes the C3X native-CAD Route A workflow used for paper validation and for
Bayesian-optimization feedback. It intentionally stays in the fluid domain:
no solid zone and no fluid-structure or conjugate heat-transfer coupling.

## 1. Reference condition

Use NASA CR-182133 run 44344 as the first validation condition.

Mainstream:

- pressure inlet total pressure: `285130 Pa`
- pressure inlet total temperature: `701 K`
- inlet turbulence intensity: `6.5%`
- pressure outlet static pressure: `170416.542 Pa`

Coolant experimental supply values, with zero Fluent operating pressure:

| Zone | Region | Pc/Pt | Total pressure [Pa] | Total temperature [K] | 14.85 mm slice mdot target [kg/s] |
|---|---|---:|---:|---:|---:|
| `qian` | leading edge / showerhead | 1.048 | 298816.240 | 602.86 | 0.0012433465 |
| `ss` | suction side | 1.051 | 299671.630 | 595.85 | 0.0026114173 |
| `ps` | pressure side | 1.050 | 299386.500 | 581.83 | 0.0014655118 |

For the current `14.85 mm` periodic optimization slice, impose the measured
slice mass flows and total temperatures as the primary NASA external-flow
validation boundary condition. The slice uses a simplified spanwise hole
density and does not exactly reproduce the NASA full-span `P/D=4` layout, so
using `Pc/Pt` to predict coolant flow would mix a known geometric simplification
into the aerodynamic validation. Retain the listed `Pc/Pt` values as diagnostic
targets and report the inlet total pressure required to realize each imposed
mass flow. A future exact-pitch/full-span model may restore pressure inlets as a
strict coolant-supply prediction test.

The Kumar paper lists the same validation values in a different verbal order.
For this project, NASA table order controls; do not swap the coolant regions to
match Kumar's wording.

## 2. Thermal wall modes

Run two wall modes as separate cases:

1. `adiabatic`: no-slip, zero heat flux. This is the BO and adiabatic
   film-effectiveness mode.
2. `isothermal`: no-slip, specified wall temperature. This is the heat-transfer
   validation mode for heat flux, HTC, Stanton, or Nusselt comparisons.

Do not combine these in one run. Do not add CHT unless the project scope changes.

NASA Table VI gives the arc-weighted average `Tw/Tg = 0.79`, while Table VIII
contains local surface position, `Tw/Tg`, and heat-transfer data for each run
code, including 44344. The uniform `Tw=553.79 K` case is therefore only the
first pipeline check; the publication-grade prescribed-temperature run should
use the local Table VIII profile.

For the no-CHT thermal validation, run the following pair on the identical mesh:

1. `nasa_44344_snr_fc`: measured 44344 coolant mass flows, `Tw=553.79 K`;
2. `nasa_44344_snr_nfc`: zero net mass flow at all three plenum inlets,
   `Tw=553.79 K`.

With common mainstream and wall temperatures, compute

```text
SNR = 1 - St_FC/St_NFC = 1 - q_FC/q_NFC
```

after area averaging `q_FC` and `q_NFC` in each surface-distance bin. Do not
average pointwise ratios near hole exits because the NFC heat flux can approach
zero and create nonphysical spikes.

### 2.1 Validation claims and their limits

NASA CR-182133 does **not** provide an adiabatic film-effectiveness data set that
can be compared directly with the present fluid-only model. Its measured wall
temperature and external heat-transfer coefficient depend on the metal vane,
internal radial cooling passages, and a conduction reconstruction. Consequently:

- NASA run 44344 is used first to validate the aerodynamic response at measured
  coolant flow: vane surface pressure distribution, exit condition, mass balance,
  and stable resolved-hole flow. Required coolant inlet total pressures are
  compared with NASA `Pc/Pt` as a secondary geometry/supply diagnostic;
- NASA Figure 30 run 44344 provides the primary experimental SNR trend; the
  current digitization is approximate and must not support a high-precision
  RMSE claim;
- a later specified-wall-temperature run should impose the local Table VIII
  wall-temperature distribution; this remains fluid-only and requires no CHT;
- adiabatic effectiveness from the NASA-aligned case is a project prediction,
  not a directly NASA-validated experimental observable;
- Kumar Figures 6 and 7 may be used as a **numerical film-effectiveness
  benchmark**, not described as NASA experimental validation.

The paper must therefore use wording equivalent to "validated against NASA flow
and heat-transfer data" and "film effectiveness benchmarked against Kumar's
numerical results". It must not claim NASA experimental validation of adiabatic
effectiveness.

### 2.2 Film-effectiveness benchmark cases

Use an adiabatic vane wall and reproduce Kumar's published extraction locations:

| Benchmark | Geometry | Operating point | Comparison quantity |
|---|---|---|---|
| pressure side | forward holes, `alpha_P=30 deg` | `Pc/Pmain=1.15` | lateral `eta(Z/D)` at `X/Cax=0.31` |
| suction side | forward holes, `alpha_S=35 deg` | `Pc/Pmain=1.15` | lateral `eta(Z/D)` at `X/Cax=0.48` |

Kumar states both `Tmain=1773 K, Tc=773 K` and a temperature ratio of `3`.
These are inconsistent (`1773/773=2.294`). For direct reproduction of Figures 6
and 7, use the figure condition `Tmain/Tc=3` (`Tc=591 K`) as the primary case and
run the explicit `Tc=773 K` condition as a documented source-ambiguity
sensitivity. Do not tune unrelated model constants to force agreement.

The NASA baseline pressure-side angle is `20 deg`, so the pressure-side Kumar
benchmark requires a separate validation geometry at `30 deg`; it is not the
NASA baseline geometry used by the BO loop.

## 3. Geometry and mesh route

Use native-CAD Route A on this workstation:

```text
design JSON -> SCDOC -> Workbench/Discovery -> Fluent Meshing -> Fluent Solution
```

The Fluent case must preserve named zones:

```text
inlet, outlet, qian, ss, ps,
periodic_low, periodic_high, span_low, span_high,
vane_wall, film_hole_wall
```

Do not use SAT import, PyFluent headless watertight meshing, or
`split_merged_boundary` for Route A validation cases.

## 4. Mesh tiers

Use `configs/c3x_mesh_tiers.yaml` as the source of mesh-intent metadata.

| Tier | Fidelity | Intended use | Expected cells | Boundary-layer target |
|---|---|---|---:|---|
| `smoke` | pipeline only | boundary-name and automation check | 0.3-1.0M | coarse startup only |
| `coarse` | L1 | BO exploration and inexpensive screening | 1.5-3.0M | moderate wall resolution |
| `paper` | L2 | decision-quality RANS and routine confirmation | 3.0-5.0M | y+ near 1 target |
| `fine` | L3 | grid-convergence reference and finalist audit | 6.0-10.0M | y+ near 1 target |

For grid independence, run at least `coarse`, `paper`, and `fine` on the baseline
NASA 44344 case with the same solver settings and post-processing definitions.

Primary mesh-independence quantities:

- area-averaged wall adiabatic effectiveness over the protected vane wall;
- lateral effectiveness profiles at the fixed Kumar extraction stations;
- pressure-side and suction-side wall effectiveness summaries;
- LE/SS/PS coolant mass flows;
- mass imbalance;
- total-pressure loss metric;
- wall y+ min/mean/p95/max;
- residual history and warning counts.

Accept the paper grid if `paper -> fine` changes are small enough for the article
claim being made. Initial engineering thresholds:

- `eta_bar`: less than 2-3%;
- coolant mass flow per plenum: less than 1-2%;
- total-pressure loss metric: less than 2-3%;
- y+ compatible with the selected wall treatment.

### 4.1 Quantity-specific grid claims

Grid independence is a claim about a reported quantity, not about the mesh in
the abstract. Use the three baseline grids to demonstrate that aerodynamic
quantities such as vane pressure loading, exit condition, and mass conservation
are insensitive to refinement. Do not extend that statement automatically to
adiabatic effectiveness if `eta_bar` remains mesh dependent.

For adiabatic effectiveness, assign the optimization information levels as:

- L1: frozen one-dimensional film-cooling knowledge;
- L2: coarse CFD for low-cost design trends;
- L3: paper CFD as the high-fidelity optimization target.

The fine mesh estimates residual numerical uncertainty and audits selected
finalists outside the optimization loop.

This permits a defensible multi-fidelity study even when the fidelity levels
have different absolute effectiveness offsets. It does not permit calling an
effectiveness result grid independent before the paper-to-fine change meets the
stated tolerance.

### 4.2 Fidelity ranking validation

Ranking validation asks whether the two CFD fidelities order the same paired
designs from worse to better. For paired designs `x_i`, compare coarse
`eta_L2(x_i)` and paper `eta_L3(x_i)` using:

- Spearman rank correlation and Kendall pairwise concordance;
- top-k overlap, with the selected `k` fixed before evaluation;
- agreement in the sign of each controlled design perturbation;
- high-fidelity regret of the best low-fidelity candidate;
- the same checks for feasibility constraints and pressure loss.

An absolute offset between levels is acceptable for exploration if ordering is
stable and the offset can be learned by the multi-fidelity discrepancy model.
Frequent rank reversals mean that the cheaper level is not a reliable optimizer,
even if its mean value is close to the refined result.

Use a two-stage evidence set:

1. Before a long BO campaign, evaluate the baseline plus at least four
   deliberately varied feasible designs on coarse and paper CFD as a pilot
   ranking gate.
2. During the campaign, add paired coarse/paper points only where they improve
   cross-fidelity calibration. Audit the baseline, representative extremes, and
   an equal number of finalists from each optimization method on the fine mesh.

Initial decision criteria are `Spearman rho >= 0.9`, consistent perturbation
directions, and useful top-k overlap. These are engineering gates rather than
universal constants and must be frozen before viewing the final optimization
results. If they fail, either refine the coarse grid, model a nonlinear
cross-fidelity map, or restrict coarse CFD to regions where ordering is reliable.

## 5. Solver sequence

Startup sequence:

- steady pressure-based RANS;
- ideal-gas air;
- energy equation on;
- SST k-omega as the project baseline;
- SIMPLEC pressure-velocity coupling;
- first-order upwind for startup stability;
- conservative under-relaxation during cold start.

After a stable startup, continue the same case with second-order discretization
before generating paper-quality comparison data. A SIMPLE or realizable k-epsilon
run can be added as a Kumar-comparison sensitivity, but it is not the primary
NASA-validation route.

## 6. Convergence checks

A run is not accepted from residuals alone. Record:

- final residuals for continuity, momentum, energy, k, and omega;
- residual trends over the final 100-300 iterations;
- mass imbalance;
- reversed-flow warnings at pressure outlet;
- artificial-wall warnings;
- coolant inlet backflow or choking symptoms;
- y+ distribution on all walls.

For the adiabatic-wall baseline, export effectiveness at checkpoints separated
by at least 300 solver iterations. A provisional thermal plateau requires both
whole-wall and protected-area effectiveness to change by no more than `3%`
relative to the preceding checkpoint. This is an engineering stopping gate,
not a claim of asymptotic convergence. Aerodynamic quantities may reach their
plateau substantially earlier and must be assessed separately.

Temperature-limited cells are not accepted or rejected from their count alone.
Record the affected cell count and zones, confirm whether wall values touch the
solver limits, and repeat the reported integral after clipping locally
out-of-range effectiveness to `[0, 1]`. A run may be retained for an integral
eta objective only when the affected fraction is small, the wall is not pinned
to the solver bounds, and the objective perturbation is explicitly negligible
under the study's frozen tolerance. Such a run remains unsuitable for local
temperature or heat-transfer validation near the affected region.

Initial run gates for BO screening:

- no divergence or floating-point exception;
- mass imbalance below `1e-3` of inlet mass flow when available;
- stable or decreasing residuals;
- no persistent artificial-wall warnings on coolant inlets after startup.

Paper-validation gates should be stricter and must be stated with the final data.

## 7. Automated result contract

Every completed CFD evaluation should produce:

```text
post/
  bo_summary.json
  wall_temperature_summary.json
  wall_eta_summary.json
  wall_yplus_summary.json
  mass_flow_summary.json
  pressure_summary.json
  convergence_summary.json
```

`bo_summary.json` is the small file consumed by the BO loop. It must contain:

- `valid`: boolean;
- `objective.eta_bar`: scalar objective for adiabatic wall runs;
- `constraints.coolant_mass_flow_ratio`: actual/reference coolant mass flow if available;
- `constraints.mass_imbalance`: if available;
- `constraints.pressure_loss`: if available;
- `diagnostics`: residuals, warning counts, mesh tier, and field availability.

For adiabatic effectiveness, use the project definition:

```text
eta = (Tg_ref - Taw) / (Tg_ref - Tc_ref)
```

where `Taw` is wall temperature from the adiabatic-wall solution. The default
`Tg_ref` is the NASA 44344 mainstream total temperature. The default `Tc_ref` is
the mass-flow-target-weighted coolant total temperature from the three plenums.
Any publication figure must state the exact reference temperatures used.

`eta_bar` must be area weighted. The current implementation in
`scripts/export_workbench_film_results.py` exports face-centred wall
temperature, face centroids, and face-area vectors, and computes a true
face-area-weighted mean. Nodal arithmetic means are not accepted for grid
independence, BO ranking, or paper figures.

For NASA run 44344, the mass-flow-target-weighted coolant reference temperature
is `593.6263 K`. This single reference is suitable for a global BO objective, but
it must not be presented as a local experimental coolant temperature.

Paper/validation post-processing must additionally export:

```text
post/
  eta_surface_faces.csv
  eta_lateral_ps_xcax_0p31.csv
  eta_lateral_ss_xcax_0p48.csv
```

Paired NASA SNR validation additionally exports:

```text
post/
  wall_heat_transfer_summary.json
  heat_transfer_heat_flux_surface_faces.csv
comparison/
  snr_surface_faces.csv
  snr_surface_binned.csv
  snr_nasa_comparison.csv
  snr_validation_summary.json
  snr_nasa_comparison.png
```

Each lateral file must include at least `Z/D`, `Taw`, `eta`, face area or sample
weight, surface side, extraction tolerance, and the exact `Tg_ref/Tc_ref` used.

For the Kumar comparison, report the signed stations as `-0.31` on the pressure
side and `+0.48` on the suction side. The exporter keeps side and station
magnitude as separate fields and also emits `signed_station_X_over_Cax`.
Because the available paper description is ambiguous between axial distance
and wall arc length, retain both coordinate interpretations in the diagnostic
export and do not select one merely because it improves agreement.

## 8. Geometry feasibility gate

Before SpaceClaim/Workbench meshing, each candidate design must pass a topology
gate:

- row order is preserved on each surface;
- hole markers have valid start/end/radius definitions;
- span positions stay inside the periodic slice;
- direction probes remain consistent: passage side is outside the blade and
  plenum side is inside the blade;
- if cavity polygons are available, the hole inner end falls inside the target
  SS/PS plenum polygon with a nonzero clearance margin;
- hole spacing and hole-to-cavity clearance are above the configured minimum.

If the gate fails, the BO evaluator should return an invalid result and a penalty
without launching CAD, meshing, or Fluent.
