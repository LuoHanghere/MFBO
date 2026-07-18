# C3X Work Log

## 2026-07-15 - NASA interpretation, three-grid evidence, and multi-fidelity decision

The NASA CR-182133 review and the subsequent optimization-readiness discussion
produced the following frozen interpretation.

### NASA thermal-data scope

- NASA Figure 30 reports Stanton-number reduction, not adiabatic film
  effectiveness.
- The primary heat-transfer thermocouples lie on a fixed near-midspan
  instrumentation plane approximately 2.54 mm from midspan. The report data are
  therefore not equivalent to the current full-period spanwise area average.
- Sparse off-plane thermocouples check the assumed two-dimensional conduction
  reconstruction; they do not form a dense spanwise average.
- NASA uses a measured, nonuniform `Tw/Tg` distribution and reconstructs local
  heat transfer through a vane conduction model. The current uniform
  `Tw=553.79 K` FC/NFC pair is a pipeline approximation.
- A phase-resolved review of the current CFD showed that spanwise sampling can
  change the sign of SNR near the downstream rows, especially on the pressure
  side around 31-35% surface distance. It cannot explain all disagreement:
  the aft suction surface remains negative over nearly every sampled spanwise
  phase.
- The NASA SNR comparison is retained as a qualified local thermal-response
  benchmark. It is not used as direct experimental validation of the final
  adiabatic-effectiveness objective.

### Evidence already available

- Vane pressure loading is relatively insensitive between the current coarse
  and paper grids. NASA pressure RMSE is approximately 0.0335 and 0.0397,
  respectively; pressure-side RMSE is approximately 0.0087 and 0.0127.
- With measured NASA coolant mass flows imposed, the total pressures required
  by the resolved inlet/plenum/hole system differ from the NASA targets by
  approximately -0.005% for the leading edge, -2.66% for the suction side, and
  +2.58% for the pressure side. This pressure-flow response is an independent
  hydraulic diagnostic; the imposed mass-flow match itself is not validation.
- Mass conservation is of order 1e-7 kg/s and the accepted runs contain no
  artificial-wall, reversed-flow, divergence, or floating-point warnings.
- Absolute adiabatic effectiveness is not yet grid independent: the current
  baseline `eta_bar` changes from about 0.492 on the 1.96M coarse grid to 0.363
  on the 3.78M paper grid. This difference must be reported rather than hidden.

### Three-grid and multi-fidelity interpretation

- Retain three numerical grids, but do not equate them with the three
  optimization information levels. Use L1/one-dimensional knowledge,
  L2/coarse CFD, and L3/paper CFD. Fine CFD is an external convergence and
  finalist audit.
- Use all three baseline grids to support quantity-specific grid independence
  for aerodynamic loading if the fine result confirms the existing stability.
- Treat the differing effectiveness responses as structured fidelity bias, not
  as evidence that every grid predicts the same absolute thermal quantity.
- The core optimization question is whether fidelity levels preserve design
  ordering. Ranking validation compares the same feasible designs across
  levels using Spearman/Kendall correlation, top-k overlap, perturbation-sign
  agreement, constraint consistency, and high-fidelity regret.
- Begin with a baseline plus four deliberately varied paired coarse/paper
  designs. Use the frozen L1 knowledge at every design. Add paired CFD points
  during BO only as required by the discrepancy model, and reserve fine CFD for
  equal-count finalist audits across methods.
- Optimization may begin after the pilot ranking gate, while NASA Table VIII
  reconstruction and the L3 audit continue in parallel. Final publication
  claims are limited to relative optimization under the frozen model, with
  refined-grid confirmation of finalists.

### Publication wording boundary

The defensible claim is that aerodynamic loading and coolant pressure-flow
response are quantitatively checked against NASA, thermal behavior is compared
with the limitations of the instrumentation plane and wall-temperature model
stated, and optimization decisions are supported by cross-fidelity ranking and
refined-grid confirmation. Do not claim direct NASA validation of adiabatic
effectiveness or grid independence of `eta_bar` until the corresponding tests
pass.

## 2026-07-05 — Coupled row-position feasibility maps

- Added `scripts/plot_c3x_pair_feasibility.py`.
- Generated coupled `SS1-SS2` and `PS1-PS2` plane maps using the same fixed
  plenum polygons, hole radius, shared pair axis, and additional `0.25D` margin
  as the mandatory geometry gate.
- Outputs:
  - `configs/c3x_pair_feasibility_map.png`;
  - `configs/c3x_pair_feasibility_map.json`.
- The black zero contour is the dynamic feasibility boundary; gray marks
  reversed row order, hatching marks row gaps below `0.005 s/s0`, and blue
  dashed lines show the earlier one-row-at-a-time conditional intervals.
- Baseline clearance reserves are `0.381 mm` for the suction pair and
  `0.615 mm` for the pressure pair, consistent with the baseline geometry gate.
- The feasible regions are strongly coupled/non-rectangular, confirming that
  independent hard bounds alone cannot replace per-candidate validation.

## 2026-07-03 — Geometry/name/mesh workflow closed; plenum feasibility gate added

- User confirmed the large-side coolant-inlet review model in Discovery.
- Promoted the reviewed SS/PS/LE inlet targets into
  `configs/c3x_boundary_targets.json` and rebuilt the official baseline SCDOC.
- Official named faces after final boolean merge: `qian` face 973, `ss` face
  1047, and `ps` face 1054.
- Extracted current-coordinate SS/PS polygons from the fixed template into
  `configs/c3x_fixed_downstream_plenums.json`.
- Extended `validate_workbench_layout.py` to require the marker endpoint to be
  inside its assigned plenum with clearance for the full hole radius plus a
  configurable margin.
- Made this validation mandatory in `build_c3x_workbench_case.py`, before the
  SpaceClaim journal starts.  Production margin is `0.25D`.
- Baseline passed: 20/20 markers valid; minimum endpoint-to-plenum-boundary
  clearance is approximately `1.124 mm`.
- Negative test `SS1 s/s0=0.20` was rejected before CAD with five
  `cavity_miss` errors and no SCDOC output.
- Added `scan_c3x_row_feasible_ranges.py`.  At baseline angles and `0.25D`
  margin, one-variable-at-a-time conditional intervals are:
  - SS1: `[0.239, 0.262]`;
  - SS2: `[0.242, 0.292]`;
  - PS1: `[0.192, 0.239]`;
  - PS2: `[0.211, 0.271]`.
- These intervals seed BO but are not treated as independently combinable;
  every candidate must pass the dynamic gate.
- Locked all Route-A mesh tiers to `polyhedra`.
- Rebuilt the retained smoke mesh from the corrected official SCDOC:
  915,204 cells, one fluid cell zone, minimum orthogonal quality `0.08331`,
  surface maximum skewness `0.7840`, and unique normalized boundary names.
- Corrected coolant-inlet face counts in the final mesh are `qian=363`,
  `ss=623`, and `ps=568`; this supersedes the earlier small-end-face smoke mesh.
- Fixed a stale-output hazard in `run_fluent_native_cad_mesh.py`: an existing
  same-name MSH.H5 is explicitly removed before Fluent writes the replacement.
  Final acceptance now reloads the disk file and compares zone counts; the
  corrected mesh passed (`qian=363`, `ss=623`, `ps=568`).

## 2026-07-03 — Coolant-inlet large-side-face review model

- Diagnosed that the production target file selected the small end faces of
  the SS/PS plenums by exact centroid, while the intended supply inlets are the
  large lateral faces facing the central cavity.
- Added `configs/c3x_boundary_targets_inlet_review.json`; the production
  `configs/c3x_boundary_targets.json` remains unchanged pending visual review.
- Extended `scripts/build_c3x_workbench_case.py` with `--targets` so candidate
  face definitions can be tested without overwriting the accepted baseline.
- Generated `runs/workbench/inlet_review/c3x_wb_inlet_review.scdoc`.
- Verified one body (`fixed_fluid_domain`, 1058 faces) and retained groups
  `qian`, `ss`, `ps`, `film_hole_wall`, and all mainstream/periodic/span zones.
- Selected review faces after final boolean merge:
  - `qian`: face 973, unchanged LE inner-side face;
  - `ss`: face 1047, large SS side facing the central cavity;
  - `ps`: face 1054, large PS side facing the central cavity.
- No mesh or solver run was started for this review model.

## 2026-07-03 — Route A native SCDOC import and mesh validated

Scope: test the newly configured Fluent CAD readers and determine whether the
Workbench geometry-transfer step can be removed.

- Confirmed headless PyFluent/Fluent Meshing 2024 R2 directly imports
  `runs/workbench/baseline/c3x_wb_baseline.scdoc`.
- CAD inventory after import: one body, 1058 CAD faces, 16 initial face zones;
  named selections including `film_hole_wall`, `qian`, `ss`, and `ps` were
  recognized.  Model dimensions were correctly interpreted in metres.
- Added `scripts/probe_fluent_cad_import.py` for a cheap import-only check.
- Added `scripts/run_fluent_native_cad_mesh.py` for Route A:
  native SCDOC -> surface mesh -> topology description -> boundaries/regions ->
  prism layers -> polyhedral volume mesh -> stable zone names -> MSH.H5.
- Corrected the Fluent 24.2 boundary-layer arguments: `OffsetMethodType` must
  be `smooth-transition`; `first-height` is not an allowed method value.
- Fresh Route-A workflows successfully create `smooth-transition_1`; the old
  Workbench duplicate-child blockage does not occur.
- Validated smoke mesh on 8 processes:
  - 915,461 cells;
  - one merged fluid cell zone;
  - minimum orthogonal quality 0.08013;
  - surface maximum skewness 0.7840;
  - 8 requested prism layers;
  - clean boundary names after normalization.
- Retained result:
  `runs/direct_cad/smoke/baseline_native_final.msh.h5` and its zone inventory.
- Controlled negative test: `UseBodyLabels=No` caused native SCDOC PartMgr
  `AttachAssembly()` to fail; keep `UseBodyLabels=Yes` on this machine.
- Poly-hexcore was also generated, but it retained separate prism/core cell
  zones and split `*-quad` boundary zones.  Production was subsequently locked
  to polyhedra.
- Updated `scripts/inspect_fluent_mesh_zones.py` to work with the Fluent 24.2
  MeshingUtilities API and export JSON inventories.
- No flow solution was started.

Next gate: run topology validation and NASA setup against the retained native
CAD mesh, then move coarse/paper/fine mesh generation from Route B to Route A.

## 2026-07-01 — Route B NASA 44344 validation/BO pipeline cleanup

Scope: Workbench Route B, NASA CR-182133 run 44344 boundary-condition alignment,
automatic post-processing, and BO-ready result recording. No new Fluent
iteration was run in this step; existing `startup100` case/data were reused.

### Implemented

- Added `docs/c3x_nasa_validation_protocol.md`.
  - Fixes NASA 44344 mainstream/coolant boundary conditions.
  - Separates adiabatic BO mode from isothermal heat-transfer validation mode.
  - Defines mesh tiers, grid-independence quantities, convergence checks, and
    BO result contract.
- Added `scripts/validate_workbench_layout.py`.
  - Validates Route B layout JSON before CAD/Workbench meshing.
  - Checks row ordering, marker definitions, marker length, span positions, and
    direction probes.
  - Cavity polygon checks are optional and must use a cavity file in the same
    coordinate frame as the Route B layout.
- Added `scripts/export_workbench_film_results.py`.
  - Reads a Workbench Fluent case/data pair and writes automated summaries.
  - Exports wall temperature, wall y+, adiabatic effectiveness, pressure
    diagnostics, convergence diagnostics, and mass-flow reports.
  - Uses Fluent report definitions for mass-flow extraction.
- Added `scripts/write_workbench_run_manifest.py`.
  - Collects geometry, topology, case/data, post-processing, and convergence
    data into one manifest JSON per CFD evaluation.

### Baseline startup100 post-processing result

Input case/data:

- `runs/workbench/baseline/c3x_wb_baseline_startup100_nopatch.cas.h5`
- `runs/workbench/baseline/c3x_wb_baseline_startup100_nopatch.dat.h5`

Generated:

- `runs/workbench/baseline/post_startup100/bo_summary.json`
- `runs/workbench/baseline/post_startup100/mass_flow_summary.json`
- `runs/workbench/baseline/post_startup100/pressure_summary.json`
- `runs/workbench/baseline/post_startup100/wall_eta_summary.json`
- `runs/workbench/baseline/post_startup100/wall_yplus_summary.json`
- `runs/workbench/baseline/c3x_wb_baseline_startup100_manifest.json`

Key values from the 100-iteration startup field:

| Quantity | Value |
|---|---:|
| `eta_bar` | 0.527382 |
| coolant mass-flow ratio vs NASA target | 0.846098 |
| mass imbalance | -5.272e-05 kg/s |
| y+ mean / p95 / max | 32.52 / 51.54 / 68.28 |
| diagnostic total-pressure drop | 40577.58 Pa |
| final continuity residual | 2.6938e-02 |
| final energy residual | 5.4178e-06 |
| artificial-wall warnings | 59 |
| reversed-flow warnings | 12 |

Coolant inlet mass-flow extraction:

| Zone | Actual [kg/s] | NASA target [kg/s] | Actual/target |
|---|---:|---:|---:|
| `qian` | 0.00102312 | 0.00124335 | 0.822876 |
| `ss` | 0.00236668 | 0.00261142 | 0.906282 |
| `ps` | 0.00111167 | 0.00146551 | 0.758557 |

Interpretation: the result is a startup smoke field, not a validated NASA-aligned
solution. It proves that post-processing and mass-flow extraction work. It does
not yet satisfy the coolant-flow target or mesh-quality requirements for the
paper.

### Cleanup decisions

Safe to remove after integration:

- `fluent_*_probe.json` files under `runs/workbench/baseline/post_startup100/`.
  These only recorded temporary API probing used to find Fluent report-definition
  calls.
- `.cache_workbench_film_nasa44344_fo1000_live.txt` and
  `.cache_workbench_film_nasa44344_fo1000_err.txt`. The 1000-step run was
  intentionally aborted before useful iteration data were produced.
- Misleading topology scratch files:
  - `runs/workbench/baseline/c3x_wb_baseline_topology_check.json`
  - `runs/workbench/baseline/c3x_wb_baseline_topology_check_user_plenums.json`

Keep:

- `runs/workbench/baseline/c3x_wb_baseline_topology_check_no_cavities.json`
- `runs/workbench/baseline/post_startup100/*` official summaries
- `runs/workbench/baseline/c3x_wb_baseline_startup100_manifest.json`

### Open items

1. Workbench mesh-tier standardization:
   - map `smoke/coarse/paper/fine` from `configs/c3x_mesh_tiers.yaml` to actual
     Workbench/Fluent Meshing settings;
   - record actual cell/face/node counts for each mesh tier.
2. Grid independence:
   - run baseline NASA 44344 on `coarse`, `paper`, and `fine`;
   - compare `eta_bar`, coolant mass flow, total-pressure diagnostic/loss,
     mass imbalance, residual history, and y+.
3. Solver progression:
   - use SIMPLEC + first-order for startup;
   - continue stable runs with second-order discretization before paper-quality
     comparison.
4. Geometry feasibility:
   - use `validate_workbench_layout.py` as the BO pre-CAD gate;
   - add same-frame cavity polygon checks once the current Workbench cavity
     extraction is confirmed.

## 2026-07-01 — Grid-independence pipeline prepared

Scope: prepare the next step for baseline `coarse/paper/fine` Workbench meshes
without launching a new Fluent iteration.

### Implemented

- Added `docs/c3x_workbench_mesh_tiers.md`.
  - Records the Workbench GUI convention for `coarse`, `paper`, and `fine`
    baseline meshes.
  - Defines expected exported mesh-case paths:
    - `runs/workbench/grid_independence/coarse/baseline_coarse_mesh.cas.h5`
    - `runs/workbench/grid_independence/paper/baseline_paper_mesh.cas.h5`
    - `runs/workbench/grid_independence/fine/baseline_fine_mesh.cas.h5`
- Added `scripts/run_workbench_validation_pipeline.py`.
  - Standardizes the post-mesh automation:
    `topology check -> setup -> iterate -> export -> manifest`.
  - Accepts a Workbench-exported `.cas.h5` through `--case-in`.
  - Writes tier outputs under `runs/workbench/grid_independence/<tier>/`.
- Added `scripts/summarize_workbench_grid_independence.py`.
  - Aggregates `*_manifest.json` files into:
    - `grid_independence_summary.csv`
    - `grid_independence_summary.md`
- Updated `scripts/write_workbench_run_manifest.py`.
  - Manifest now records the raw Workbench mesh case path via `--mesh-case`.

### Verification

- Static syntax checks passed for:
  - `run_workbench_validation_pipeline.py`
  - `summarize_workbench_grid_independence.py`
  - `write_workbench_run_manifest.py`
- Performed a `--dry-run` for `baseline_coarse`; command ordering and paths were
  correct.
- Removed dry-run artifacts and empty summary files after verification.

### Next action

Stabilize Workbench batch mesh generation, especially boundary-layer insertion,
before launching the three production mesh tiers.

## 2026-07-01 - Workbench batch mesh automation status

Scope: answer whether mesh generation can be controlled by Codex/automation
rather than being fully manual.

### Implemented / verified

- Added and debugged `scripts/run_workbench_mesh_tier.py`.
- Confirmed `RunWB2 -B -F 1.wbpj -R <journal>` can open the `FLTG` system and
  send commands into Fluent Meshing.
- Confirmed Workbench batch can:
  - import `1_files/dp0/Disco/DM/Disco.dsco` with `UseBodyLabels = Yes`;
  - generate the surface mesh;
  - describe fluid-only geometry;
  - update `inlet/qian/ss/ps` boundary types;
  - generate a polyhedra volume mesh;
  - write `.msh.h5` using `meshing.File.WriteMesh(FileName=...)`.
- Smoke validation file was generated successfully:
  `runs/workbench/grid_independence/smoke_probe/baseline_smoke_writeprobe_mesh.msh.h5`.
- Solver setup validation succeeded on that generated mesh:
  - `inlet`, `outlet`, `qian`, `ss`, `ps`, `vane_wall`, `periodic_high`,
    `periodic_low`, `span_high`, and `span_low` were preserved;
  - pitch periodic `periodic_low <-> periodic_high` and span periodic
    `span_low <-> span_high` were created;
  - setup case write succeeded.

### Remaining blocker

- Boundary-layer insertion through
  `workflow.TaskObject['Add Boundary Layers'].AddChildAndUpdate(...)` still
  fails in Workbench batch with a generic command error.
- Therefore `coarse/paper/fine` production meshes should not be launched yet
  unless the boundary-layer step is fixed or deliberately performed through a
  documented GUI fallback.

### Cleanup decision

- The no-boundary-layer smoke mesh/setup case are process artifacts only. They
  validate automation plumbing but are not scientifically useful for NASA-aligned
  results and can be deleted after this record is written.

## 2026-07-01 - Boundary-layer batch blockage diagnosed

Scope: inspect why Workbench batch meshing kept failing at `Add Boundary Layers`.

### Findings

- The latest failed `baseline_smoke` journal had a quoting bug:
  `Command="(%py-exec "workflow...")"` was invalid IronPython syntax, so that
  run did not actually reach Fluent Meshing boundary-layer execution.
- Earlier true failures were different:
  `Arguments.set_state(...)` succeeded, but
  `workflow.TaskObject['Add Boundary Layers'].AddChildAndUpdate(...)` returned
  `Generic Command`.
- A Workbench task probe showed:
  - `Add Boundary Layers` is a `Compound` task;
  - its default template has
    `LocalPrismPreferences.IgnoreBoundaryLayers = yes`;
  - the project already contains a child control named `smooth-transition_1`.
- The generated `.wft` confirmed that repeated `AddChildAndUpdate` was trying
  to add another child even though `smooth-transition_1` already existed.

### Implemented

- Updated `scripts/run_workbench_mesh_tier.py` to:
  - emit Workbench `%py-exec` commands using safe Python string literals;
  - avoid f-strings inside Workbench journals for IronPython compatibility;
  - explicitly set `AddChild = yes`, `OffsetMethodType = smooth-transition`,
    `FirstHeight`, `Rate`, and
    `LocalPrismPreferences.IgnoreBoundaryLayers = no`;
  - fall back from failed `AddChildAndUpdate` to updating the existing
    `workflow.TaskObject['smooth-transition_1']` child and executing it.

### Verification

- Smoke probe with `--prism-layers 2` succeeded:
  - `AddChildAndUpdate` still failed, as expected for an existing child;
  - `UpdateExistingChildArguments` succeeded;
  - `ExecuteExistingChild` succeeded;
  - mesh write succeeded.
- The saved workflow confirmed `smooth-transition_1` changed to:
  - `NumberOfLayers = 2`;
  - `FirstHeight = 2.0e-05 m`;
  - `Rate = 1.2`;
  - `IgnoreBoundaryLayers = no`.

### Remaining verification before production tiers

- The generated smoke mesh still had `387827` cells, matching the original
  Workbench mesh, and boundary-layer flag counts were unchanged.
- Therefore the next check is not API access anymore; it is mesh sensitivity:
  run two smoke tiers with intentionally different layer counts/first heights
  and confirm the volume mesh statistics change before launching
  `coarse/paper/fine`.

## 2026-07-05 - Cooling-effectiveness validation scope fixed

Scope: define what the current fluid-only C3X model can validate without solid
conduction or conjugate heat transfer.

### Source audit

- NASA CR-182133 wall temperatures and external heat-transfer coefficients were
  obtained from a metal vane with internal radial cooling and a conduction
  reconstruction. They are not direct adiabatic-effectiveness measurements.
- Kumar Figure 5 compares `Tw/Tms` with Hylton/NASA data and uses radial-channel
  boundary conditions; it is not a direct target for the present fluid-only
  adiabatic model.
- Kumar Figures 6 and 7 provide numerical lateral film-effectiveness profiles at
  `X/Cax=0.31` (pressure side) and `0.48` (suction side), respectively.

### Decision

- Use NASA run 44344 to check flow realization, coolant mass flow, pressure/exit
  behavior, and later Stanton/HTC with a measured specified wall-temperature
  profile if those data are digitized.
- Use separate adiabatic benchmark geometries to reproduce Kumar's lateral
  effectiveness profiles. Describe this as a numerical benchmark, not NASA
  experimental validation.
- Preserve the no-CHT/no-FSI scope.

### Post-processing correction (resolved 2026-07-05)

`wall_eta_summary.json` now uses a face-area-weighted `eta_bar`, and the exporter
produces the two fixed-station lateral `eta(Z/D)` profiles from face-centred
data. The coarse Kumar run exercised this path successfully.

## 2026-07-05 - Kumar case 1 coarse result and paper retry

### Completed

- Generated native-CAD polyhedral meshes with named boundaries preserved:
  - coarse: `1,863,861` cells, 15 prism layers, first height `0.005 mm`;
  - paper: `3,586,885` cells, 25 prism layers, first height `0.002 mm`;
  - fine: `6,106,964` cells, 30 prism layers, first height `0.0015 mm`.
- Ran Kumar case 1 coarse in single precision on 16 cores. Fluent stopped at
  approximately iteration 953 after meeting its convergence criterion.
- Coarse result: area-weighted `eta_bar=0.4028061`, mass imbalance
  `1.49e-6 kg/s`, wall `y+` p95 `6.55`, maximum `8.39`.
- Replaced the nodal effectiveness average with face-area weighting and changed
  the fixed-station profile extraction to scattered interpolation at the exact
  requested station.
- Digitized Kumar Figures 6 and 7 and generated automated alignment plots and
  metrics. The signed paper stations are recorded as pressure side `-0.31` and
  suction side `+0.48`.

### Coarse comparison diagnostic

- Pressure side: RMSE `0.2857`, mean CFD `0.2796`, mean reference `0.4540`.
- Suction side: RMSE `0.1907`, mean CFD `0.4895`, mean reference `0.3239`.
- This is not yet an acceptance result: the coarse wall resolution misses the
  target `y+<1`, and the paper coordinate description remains ambiguous between
  signed axial distance and signed surface arc length.

### Paper-run status

- The paper setup case was created successfully with Realizable k-epsilon,
  SIMPLE, adiabatic walls, and the Kumar/NASA-aligned boundary conditions.
- A previous hybrid initialization reached Fluent but failed in AMG/FPE.
- A standard-initialization retry used unsuitable default absolute pressure and
  then lost the Fluent server connection.
- After the reported license restart, an 8-core single-precision hybrid retry
  on 2026-07-05 failed before reading the case: Fluent exited and PyFluent
  received localhost connection refusal `10061`.
- The environment points to `1055@localhost`, but `ANSYS, Inc. License Manager
  CVD` is stopped and port 1055 is not listening. Starting that service requires
  administrator rights outside the current Codex process.

### Resume command

Once the local ANSYS License Manager is genuinely running, resume with:

```powershell
.\.venv\python.exe scripts\run_workbench_validation_pipeline.py `
  --name kumar_case1_paper --tier paper `
  --case-in runs\direct_cad\paper\kumar_case1_paper.msh.h5 `
  --simulation-case kumar_case1_tr3 --iters 1000 --startup-iters 200 `
  --initialization hybrid --cores 8 --precision single `
  --out-root runs\kumar_validation --skip-setup
```

Do not launch fine until paper converges and its mass balance, wall `y+`, and
profile-coordinate interpretation have been reviewed.

## 2026-07-06 - Paper result, hot-cell localization, and Kumar sampling audit

### Paper run completed

- The single-precision paper case completed on 16 cores and Fluent stopped at
  iteration 387 using its default convergence check.
- The solution did not diverge or report an FPE. The final mass imbalance was
  approximately `1.03e-5 kg/s` (`0.0078%` of outlet mass flow).
- The area-weighted wall effectiveness was `eta_bar=0.3927001`; wall `y+` mean,
  p95, and maximum were `0.968`, `2.128`, and `2.876`.
- This stop criterion is less strict than the Kumar protocol (`1e-5` flow and
  `1e-8` energy residuals); future production runs must set those thresholds
  explicitly rather than relying on Fluent defaults.

### Temperature-outlier localization

- Direct HDF5 inspection found exactly three cells at the `5000 K` limiter,
  all in cell zone 319 (`fixed_fluid_domain`): IDs `958137`, `958175`, and
  `958713`.
- Their reconstructed diagnostic locations cluster around the leading edge
  (`x=-0.62...1.18 mm`, `y=107.3...114.3 mm`). Their vertex bounds extend over
  a large part of the periodic span, which is consistent with a local
  periodic-interface/polyhedral-connectivity artifact rather than a global
  wall-temperature problem.
- On the vane wall, `99.931%` of area lies between the coolant and mainstream
  reference temperatures. The area above mainstream temperature is only
  `0.0428%`; the area below coolant temperature is `0.0261%`.
- Removing those out-of-range wall faces changes `eta_bar` from `0.3927001` to
  `0.3927663`, so their effect on the global cooling conclusion is negligible.
- Reusable outputs: `post_iter1000/hot_cell_diagnostics.{json,csv}` and
  `post_iter1000/hot_cell_locations.png`; generator:
  `scripts/inspect_fluent_hot_cells.py`.

### Kumar extraction audit

- Rechecked the paper text and Figures 6/7. The fixed stations remain pressure
  side `|X/Cax|=0.31` (reported as signed `-0.31`) and suction side
  `X/Cax=+0.48`, in the stagnation-point axial coordinate convention.
- Neither station intersects the localized high-temperature region. In a
  `+/-0.01 X/Cax` band, pressure-side wall temperatures are `581...1674 K`
  and suction-side wall temperatures are `1182...1329 K`.
- A station sweep was retained only as a diagnostic. Moving the station can
  reduce scalar RMSE, but the pressure-side minimum at `X/Cax=0.50` has negative
  shape correlation, so it is not a defensible coordinate correction. Do not
  tune the sampling station to fit the reference curve.
- At the published stations and common digitized `Z/D` points, the pressure
  side has RMSE `0.2260`, mean bias `-0.1217`, and correlation `0.353`; the
  suction side has RMSE `0.1560`, mean bias `+0.1152`, and correlation `0.730`.
- Reusable outputs: `post_iter1000/kumar_sampling_audit.{json,png}`; generator:
  `scripts/audit_kumar_sampling.py`.

### Extended sampling-coordinate hypotheses (2026-07-06)

- The audit was extended over almost the full axial surface range instead of
  assuming the published values are absolute coordinates.
- Pressure side: interpreting `0.31 Cax` as a distance downstream of the last
  pressure-side row gives absolute `X/Cax=0.6114` and reduces RMSE from `0.2260`
  to `0.0684`, but shape correlation changes from `+0.353` to `-0.387`. This is
  primarily a mean-level match after the CFD profile becomes nearly uniform.
- Suction side: the analogous relative-distance interpretation gives
  `X/Cax=0.8925`, worsens RMSE from `0.1560` to `0.1801`, and reduces shape
  correlation from `+0.730` to `-0.068`.
- The suction-side minimum-RMSE station is `X/Cax=0.4004`, but it lies upstream
  of the last suction-side row at `0.4125`; it cannot represent a downstream
  sampling plane. The pressure-side global RMSE minimum is near the trailing
  edge and has essentially zero shape correlation.
- Decision: retain all candidate curves as coordinate-sensitivity evidence.
  The absolute stations remain the only single convention that is physically
  consistent on both sides; do not select different definitions side by side
  solely to minimize error.

## 2026-07-06 - BO objective-area audit

- The exported value `eta_bar=0.3927001` is mathematically correct for the
  entire `vane_wall`, using `Tg=1773 K`, `Tc=591 K`, and a true face-area
  weighting. It corresponds to area-weighted `Taw=1308.83 K`.
- The written optimization definition, however, specifies the protected area,
  while the current exporter averages the complete vane. This includes fixed
  leading-edge/upstream regions that are weakly affected by the four variable
  downstream rows and therefore dilutes BO sensitivity.
- A provisional controllable protected-region mask was audited: pressure side
  downstream of the first variable row (`X/Cax>=0.26530`) plus suction side
  downstream of the first variable row (`X/Cax>=0.37638`). This covers `77.51%`
  of the vane-wall area and gives baseline `eta_bar=0.4631238`.
- The same protected-area value is `0.4733746` on coarse and `0.4631238` on
  paper, a `2.17%` change. The complete-wall value changes by `2.51%`.
- Protected-region coverage is much better behaved: area-weighted fifth
  percentile effectiveness is `0.3189`, and only `1.39%` of its area has
  `eta<0.2`. For the complete wall those figures are `0.0132` and `13.67%`.
- Recommendation pending explicit approval: freeze the protected-region mask
  before BO, use its `eta_bar` as the primary objective, retain complete-wall
  `eta_bar` as a reported diagnostic, and track a low-percentile/low-coverage
  metric so a high mean cannot hide local hot regions.
# 2026-07-10 - Physical-pitch external flow, CAD rebuild, and smoke acceptance

- Froze pitch periodicity at `T = [0, 117.73] mm` in the cascade `x/y` frame.
- Confirmed vertical inlet/outlet end caps, pointwise translated side walls, and
  three adjacent non-overlapping C3X vanes.
- Added `scripts/check_periodic_tiling.py`; its periodic-v2 report records a
  `2.84e-14 mm` side-wall mismatch and `33.81 mm` adjacent-vane gap.
- Rebuilt the fixed template automatically from the fixed LE cavity, ten LE
  holes, and the reviewed SS/PS plenum polygons. No manual cavity construction
  is part of the periodic-v2 route.
- Rebuilt the baseline with 20 parameterized downstream holes. The pre-CAD gate
  passed all 20 markers with `1.124 mm` minimum cavity clearance versus the
  required `0.7425 mm`.
- Final CAD is one connected fluid body with named inlet/outlet, pitch/span
  periodics, three coolant inlets, vane wall, and film-hole wall.
- Native-CAD smoke mesh succeeded with `909264` polyhedral cells, eight requested
  prism layers at `0.020 mm` first height, minimum orthogonal quality `0.0877`,
  and maximum skewness `0.9123`.
- Fluent Solver created pitch periodicity with `[0, 0.11773, 0] m` and span
  periodicity with `[0, 0, 0.01485] m`; the setup case write completed.
- Smoke is a topology/automation acceptance artifact only. It is not suitable
  for NASA validation or paper results.

## 2026-07-11 - Mesh tiers, coarse result, license blocker, and BO scaffold

### Mesh and solver status

- Saved the accepted coarse mesh with `1,858,027` cells, 15 boundary layers,
  minimum orthogonal quality `0.0382`, and maximum skewness `0.9618`.
- The coarse Kumar case completed 1000 iterations. Postprocessing gave complete-
  wall `eta_bar=0.416173`, mass imbalance `7.33e-7 kg/s`, wall `y+` p95 `6.61`,
  pressure-side RMSE `0.249`, and suction-side RMSE `0.193`. This remains a
  screening fidelity rather than a paper-quality validation result.
- Saved the uniform-layer paper mesh with `3,664,014` cells. Average orthogonal
  quality improved to `0.876` and average skewness to `0.120`; rare local cells
  remain at minimum orthogonal quality `0.01076` / maximum skewness `0.98924`.
- Saved `kumar_case1_periodic_v2_paper_uniform_setup.cas.h5`. The paper solve did
  not produce a result case/data pair, and the fine mesh was not launched.

### License diagnosis and exact resume blocker

- Fluent v242 requests CFD feature version `2024.0521`; every relevant feature
  in the currently loaded `ansyslmd.lic` is version `2024.0501`.
- FlexNet returns `-25` for `acfd`, `acfd_fluent_solver`, and `1cfxmshpr` and
  reports the current license file as `Tampered`. Administrator rights and the
  Windows user-directory language do not resolve a signed feature-version
  mismatch. The file must be replaced by a legitimate v242-compatible license.
- At 21:46 the License Manager restart returned `cfd_base`, both solve levels,
  and the HPC pack held by the active Fluent process. Do not restart the license
  service while a mesh or solve is running.

### Optimization framework scaffold

- Added a persistent SQLite experiment ledger, resumable ask/evaluate/tell state
  machine, hard geometry gate, deterministic synthetic evaluator, and external
  command-pipeline adapter under `bofm/optimization`.
- Added the correlation/Sellers physics prior and an exact residual GP. The
  bootstrap acquisition is constrained expected improvement per relative cost;
  the production method remains constrained cost-aware MFKG after L1/L2
  correlation is measured.
- Added `configs/c3x_optimization.yaml`, a headless runner, and a compact Tk UI
  for start/resume, pause, stop scheduling, trial selection, cost history,
  convergence, events, and archived run access.
- The optimization controller is testable without ANSYS. Production CFD remains
  gated on license recovery, paper baseline acceptance, a frozen protected-area
  objective, and a versioned `result.json` postprocessing contract.

## 2026-07-12 - Coarse-only optimization campaign prepared

- Froze the first screening campaign to six continuous variables: four
  downstream-row arc positions and suction/pressure injection angles. Hole
  diameter remains `0.99 mm` and span count remains five.
- Added a fixed protected-area exporter and strict optimizer result contract.
  On the current periodic-v2 coarse baseline the protected region covers
  `77.45%` of vane-wall area and gives `eta_bar=0.4889209`; coolant mass and
  diagnostic pressure loss are normalized to one.
- The older `eta_bar=0.4733746` work-log value belongs to the previous
  `runs/kumar_validation/coarse` geometry, not the current periodic-v2 model.
- Imported the accepted periodic-v2 coarse result as trial 1 in
  `runs/optimization/coarse/c3x_coarse.sqlite3`, so it will not be recomputed.
- Generated four deterministic initial DoE candidates. All pass the complete
  coupled plenum/row geometry gate; their minimum cavity clearances are `0.874`,
  `1.782`, `0.817`, and `1.457 mm`.
- Added and dry-run checked the per-trial chain: parameterized SCDOC, fresh
  coarse mesh, Kumar setup, 500 iterations, postprocessing, and `result.json`.
- Live execution remains blocked by the unchanged FlexNet `-25` feature-version
  rejection. No new CFD objective has been fabricated from the prior model.

## 2026-07-13 - License recovery, paper-mesh audit, and bounded var-property test

### License and accepted constant-property result

- Real Fluent v242 launch probes succeeded in solver/meshing mode and at eight
  solver cores. The old FlexNet `-25` text was stale and is no longer treated as
  authoritative when a real launch succeeds.
- The 3,664,014-cell uniform-layer paper mesh and two repaired variants remained
  thermally unstable and are rejected. Reducing uniform layers to 18 also
  failed; cell count alone was not the cause.
- The original 3,571,905-cell smooth-transition paper mesh completed 500
  iterations. It has protected-area `eta_bar=0.4579285`, mass imbalance
  `0.01898%` of outlet flow, wall `y+` p95 `2.10`, no 5000 K cells, and 51 cells
  at 1 K.
- Clipping out-of-range wall values changes protected `eta_bar` by only
  `1.22e-5`; this result is accepted for eta screening only. It is rejected for
  pressure loss and full paper validation.
- Kumar alignment remains the main gate: pressure-side RMSE/correlation are
  `0.2439/0.236`, suction-side `0.1658/0.762`. Do not tune the extraction
  station to obtain a scalar fit.

### Local mesh repair A/B

- One `Orthogonal Quality < 0.03` volume-improvement pass on the smooth mesh
  raised minimum orthogonal quality from `0.01204` to `0.02159` and reduced
  maximum skewness from `0.98796` to `0.97841`. The saved mesh is
  `kumar_case1_periodic_v2_paper_smooth_repaired.msh.h5`.
- With the initially ineffective startup controls, the same 100-step
  variable-property test reduced 5000 K cells from 139 to 82 (41% reduction).
  A second repair pass raised the count to 112 and is rejected. Repeated global
  smoothing is not a valid substitute for a local upstream transition control.

### Temperature-dependent air and startup-control correction

- Added Kumar/Singh temperature-polynomial `Cp`, conductivity, and viscosity
  for 100--2300 K. Kumar cases now select them explicitly; NASA cases retain
  their existing property selection.
- Found and fixed silent PyFluent key mismatches. Fluent 24.2 uses `mom`,
  `temperature`, `min_temperature`, `max_temperature`, and
  `max_turb_visc_ratio`; the previous `momentum`, `energy`, and reversed limit
  names had left default URFs and limits active.
- On the once-repaired smooth mesh, a clean 100-step first-order run with
  `mom=0.5`, `temperature=0.3`, and `k/epsilon=0.4` had a fully physical
  `590.74--1767.56 K` range and zero temperature-limited cells.
- By step 200 the range was `586.61--2312.14 K`, with 22 cells above 1773 K and
  one above the polynomial validity ceiling. By step 300 the unconstrained run
  developed 29 cells at 5000 K and 13 at 1 K. A repeated step-200-to-300 run
  bounded to 100--2300 K still accumulated 41 lower-bound and 644 upper-bound
  cells. Both step-300 files are rejected.

### Current decision and next action

- Do not ignore temperature-limited cells merely because their fraction is
  small. Ignore them only for a named metric after quantifying wall-area and
  clipped-objective impact; the accepted constant-property smooth result meets
  that eta-only criterion.
- Do not continue the variable-property result to second order. Its next test
  is a local volume-size/refinement control around the upstream periodic
  transition cluster, followed by a double-precision 100/200/300-step A/B run.
- Fine mesh generation remains deferred until the paper grid passes Kumar
  pressure- and suction-side alignment checks.

## 2026-07-13 - NASA 44344 film-only coarse validation

- Built the NASA-angle periodic-v2 CAD with suction holes at `35 deg`, pressure
  holes at `20 deg`, `D=0.99 mm`, and physical hole length `3.35 mm`. The
  topology gate passed, all 20 downstream cylinders and both plenums merged,
  and the final model is one connected fluid body with exact named boundaries.
- Saved the accepted coarse mesh at `1,956,019` cells. Minimum orthogonal
  quality is `0.03746`; average orthogonal quality is `0.8471`. Vane-wall `y+`
  is `3.94` mean, `8.37` p95, and `11.72` maximum, so this remains a screening
  grid rather than the paper grid.
- A pressure-inlet diagnostic run converged through 600 iterations with mass
  imbalance `2.22e-7 kg/s`. LE and SS coolant flows were within `0.22%` and
  `3.53%` of NASA targets, but PS was `17.21%` low. This result is not accepted
  as a strict NASA supply validation because the 14.85 mm periodic slice uses
  `P/D=3`, while the NASA full-span downstream rows use `P/D=4`.
- Changed only the NASA 44344 coolant boundaries to measured slice mass-flow
  inlets; Kumar and other cases retain pressure-ratio inlets. Continued the
  converged field for 150 second-order iterations and saved the iteration-750
  mass-flow case/data pair. All three imposed flows are realized to numerical
  precision and total mass imbalance is `3.10e-7 kg/s`.
- Exit static-pressure mean is `170421.06 Pa`, versus the `170416.54 Pa` target.
  There were no reversed-flow, artificial-wall, divergence, floating-point, or
  temperature-limit warnings. Final residuals are continuity `1.99e-3`, energy
  `3.11e-5`, velocity `6.08e-7--1.89e-5`, k `6.93e-4`, and omega `3.56e-4`.
- Digitized NASA CR-182133 Table VII directly from report page 33 and compared
  the 29 `Ma2=0.90` surface-pressure points. Overall `Ps/Pt` RMSE is `0.03349`;
  pressure-side RMSE is `0.00870`, suction-side RMSE is `0.04313`, and maximum
  absolute error is `0.10922` at the suction-side mid-chord acceleration region.
- With measured mass flow imposed, required inlet total pressure differs from
  NASA by `+0.06%` for showerhead, `-2.62%` for suction, and `+2.66%` for
  pressure. These are supply-system diagnostics, not independent validation
  quantities. The result supports coarse aerodynamic alignment; the suction
  mid-surface bias and y+ require paper-grid/model sensitivity before a final
  publication validation claim.
- The pressure RMSE changed by only `0.00008` from iteration 700 to 750, while
  complete-wall eta changed from `0.47423` to `0.49209` and protected eta from
  `0.55355` to `0.57660`. Therefore the iteration-750 case is accepted for
  coarse aerodynamic validation, but its adiabatic-effectiveness field is not
  yet frozen as an optimization or mesh-independence baseline.

## 2026-07-14 - NASA 44344 3.78M paper-grid validation

- Froze the `1,956,019`-cell iteration-750 coarse result in a standard grid-
  independence manifest. Generated a second mesh from the identical NASA SCDOC
  using the paper tier: `3,776,658` cells, 25 smooth-transition prism layers,
  `0.00075 mm` first height, and `0.04--1.5 mm` surface controls.
- The raw paper mesh had minimum orthogonal quality `0.00601` and maximum
  skewness `0.99399`. One volume-improvement pass below orthogonal quality
  `0.03` raised these to `0.02096` and `0.97904` without changing cell count.
  Both raw and repaired meshes are retained; only the repaired mesh was solved.
- Applied the same NASA measured-mass-flow inlets, SST k-omega, constant-air
  properties, SIMPLEC coupling, `400--1000 K` safety limits, and pressure
  normalization as the coarse case. The paper run used 200 first-order startup
  iterations followed by 500 second-order iterations.
- At iteration 700, continuity is `7.69e-4`, energy is `1.01e-5`, velocity
  residuals are `2.19e-6--1.44e-5`, k is `5.10e-4`, and omega is `1.62e-4`.
  Mass imbalance is `-1.33e-7 kg/s`; outlet static-pressure mean is
  `170420.19 Pa` versus the `170416.54 Pa` target. There are no reversed-flow,
  artificial-wall, divergence, floating-point, or temperature-limit warnings.
- Vane-wall y+ improved from coarse mean/p95/max `3.972/8.367/11.701` to paper
  `0.993/2.361/3.436`. The mean meets the near-unity design intent; the upper
  tail remains above one and should be reported rather than hidden.
- NASA Table VII overall pressure RMSE is `0.03972` on paper versus `0.03349`
  on coarse. Pressure-side RMSE is `0.01275` versus `0.00870`; suction-side is
  `0.05077` versus `0.04313`. The finer mesh is slightly worse against the
  measurements but remains close; this is consistent with favorable numerical-
  diffusion error cancellation on coarse and is not evidence that the paper
  mesh is defective.
- With measured coolant flow imposed, paper-grid required total-pressure errors
  relative to NASA are `+0.21%` showerhead, `-1.99%` suction, and `+2.75%`
  pressure. These remain supply diagnostics, not imposed-flow validation data.
- Complete-wall eta changed from `0.34362` to `0.36290` and protected eta from
  `0.38615` to `0.41231` between iterations 600 and 700. Consequently the paper
  result is accepted for aerodynamic validation and y+ assessment, but neither
  coarse nor paper eta is accepted yet for thermal grid independence.
# 2026-07-15 - Fluid-only NASA 44344 SNR validation baseline

- Added explicit `nasa_44344_snr_fc` and `nasa_44344_snr_nfc` cases. Both use
  a prescribed `553.79 K` vane wall; the NFC case imposes zero net mass flow at
  `qian`, `ss`, and `ps`. No solid zone or CHT is used.
- Reused the accepted coarse mesh (`1,956,019` cells) and the converged
  adiabatic 44344 solution. FC was continued for 250 iterations and NFC for 300
  iterations. Both completed without divergence, floating-point errors, or
  reversed-flow warnings.
- NFC final residuals: continuity `1.91e-3`, x/y/z velocity approximately
  `1.36e-6 / 4.36e-6 / 1.85e-7`, energy `2.72e-5`; reported coolant net mass
  flow is exactly zero on all three plenum inlets.
- Exported all `26,831` vane-wall faces for heat flux, Stanton number, surface
  HTC, wall-adjacent HTC, and wall-adjacent temperature. FC/NFC face pairing is
  exact (`max distance = 0`).
- First comparison against approximate NASA CR-182133 Figure 30 run 44344 data:
  overall RMSE `0.335`; pressure-side RMSE `0.247`; suction-side RMSE `0.400`.
  The pressure-side mid-chord cooling benefit is reproduced qualitatively, but
  suction-side SNR falls below zero after about `68%` surface distance while
  NASA remains near `0.23-0.25`. This baseline is **not** accepted as a
  quantitative thermal validation.
- The next thermal-validation action is to digitize the exact run-44344 Table
  VIII local wall-temperature profile and rerun the same paired fluid-only
  calculation. Do not add cells or CHT to address this discrepancy first.
- Reproducible outputs:
  `runs/nasa_44344/snr_validation/coarse/{fc,nfc,comparison}`.

## 2026-07-15 - NASA three-grid baseline frozen

- Corrected the fine-tier first prism height from `0.0015` to `0.0005 mm` and
  generated a `6,433,128`-cell fine mesh with 30 prism layers. Two volume-
  improvement passes raised minimum orthogonal quality from `0.00641` to
  `0.01051`; maximum skewness is `0.98949`.
- Cross-mesh paper-to-fine Fluent interpolation was rejected after a 16-core
  out-of-memory failure and a four-core segmentation fault. Fine setup succeeds
  at four cores and the solve is stable at eight cores on the 32 GB workstation.
- Continued all three adiabatic baselines until the frozen 300-400 iteration
  thermal-checkpoint change was at most `3%`. Final iterations are coarse 1800,
  paper 2500, and fine 2000. Earlier coarse-750 and paper-700 values were
  materially underconverged thermally despite acceptable pressure fields.
- Final whole-wall eta is `0.57407/0.54953/0.49393` and protected eta is
  `0.68221/0.64895/0.58152` for coarse/paper/fine. The paper-to-fine changes are
  `-10.12%/-10.39%`, so eta is not declared grid independent. Optimization uses
  L1 knowledge, L2 coarse, and L3 paper; fine remains an external audit.
- NASA pressure RMSE is `0.03519/0.03260/0.03802`; pressure-side RMSE is
  `0.00741/0.01002/0.00886`. Outlet static pressure, coolant mass flow, and mass
  conservation remain aligned across grids. Aerodynamic mesh insensitivity is
  accepted for the stated quantities.
- Structured temperature-limit parsing was added. Paper reaches 1000 K in one
  fluid cell; fine reaches at most 86 low-limit and 1,393 high-limit cells. No
  fine wall value is pinned to a limit, and clipping local eta to `[0,1]`
  changes the fine whole-wall integral by `-0.31%` relatively. Fine is accepted
  for integral eta audit, not local thermal validation near affected cells.
- Generated a controlled five-design ranking pilot (baseline plus four one-
  factor perturbations). Every design passes the coupled plenum geometry gate;
  paired coarse/paper CFD is the next validation action before BO starts.
- Full decision record: `docs/c3x_nasa_three_grid_validation.md`. Ranking plan:
  `docs/c3x_nasa_ranking_pilot.md`.

## 2026-07-15 - Optimization hierarchy and comparison target corrected

- The three optimization information levels are now frozen as L1 low-order
  film-cooling knowledge, L2 coarse CFD, and L3 paper CFD. Fine CFD is not an
  optimizer fidelity; it is an independent numerical audit for equal numbers
  of selected finalists from each method.
- The primary research outcome is reduction in the number of converged paper-
  grid design evaluations, `N_HF`. Fluent iterations inside a single case are
  convergence work and are not the sample-efficiency metric.
- Standard MFBO uses only coarse + paper CFD and no physics mean. The proposed
  PI-MFBO uses the identical CFD data, initialization, acquisition, seeds, and
  budgets while adding the frozen L1 knowledge model. This isolates the value
  of prior knowledge from the ordinary benefit of multi-fidelity CFD.
- Required controls are random/LHS, paper-only BO, standard coarse/paper MFBO,
  knowledge-informed paper-only BO, proposed PI-MFBO, and wrong-prior ablation.
  All paper evaluations used for pilot calibration or initialization count in
  `N_HF`.
- Frozen benchmark protocol: `docs/c3x_optimization_benchmark_protocol.md`.

## 2026-07-16 - First real NASA MFBO paired design

- Added the shared NASA production evaluator from optimizer `design.json` through
  geometry, native-CAD Fluent meshing, optional paper-grid repair, NASA setup,
  fixed-iteration solve, postprocessing, and strict `result.json`. The runner
  now supports artifact-based resume and preserves the Fluent solve transcript.
- Seeded both comparison ledgers with the accepted paired baseline. PI-MFBO has
  L1 knowledge + L2 coarse + L3 paper; standard MFBO has the identical L2/L3
  CFD values and no prior. Shared deterministic CFD is charged at nominal cost
  in every ledger even when its artifacts are reused.
- Corrected the prior implementation: deterministic L1 is no longer inserted as
  a same-scale CFD observation. The residual GP uses only L2/L3; the physics
  mean is anchored at the declared L3 baseline. Prior variance decays with L3
  data, and a strictly positive annealed piBO-style acquisition weight biases
  rather than removes candidate support. This is not yet a no-regret proof.
- Ran the first common LHS design through both fidelities. Coarse has 1,877,557
  cells; protected eta rose from `0.68221049` to `0.69209765` (`+1.449%`).
  Paper has 3,555,118 cells; one repair pass raised minimum orthogonal quality
  from `0.01543` to `0.02136`; protected eta rose from `0.64894961` to
  `0.65747956` (`+1.314%`). The improvement direction is preserved.
- Both results pass the contract. Coarse/paper coolant mass ratios are
  `0.9999997/0.9999994`, continuity residuals `3.66e-3/1.20e-3`, and y+ p95
  `8.50/2.44`. Pressure-loss ratios are `1.192/0.992`; this cross-fidelity
  disagreement confirms pressure loss must remain diagnostic in the first
  benchmark rather than an unqualified `5%` hard constraint.
- One baseline/candidate pair cannot establish rank correlation. Complete the
  remaining controlled paired pilot or at least three additional common LHS
  pairs before claiming coarse-to-paper ranking utility.
- This design required about 79 minutes for the complete coarse pipeline and
  about 194 minutes for the resumed paper solve pipeline, plus approximately
  7 minutes for paper meshing and repair. The observed coarse/paper wall-time
  ratio is about `0.39`, so the configured `0.20` relative cost remains a
  placeholder. Freeze cost from the median wall-clock and core-hour values of
  at least three common designs rather than retuning it from one observation.
- Machine-readable record:
  `runs/optimization/pipeline_smoke/LHS_0001/paired_summary.json`.

## 2026-07-16 - First requested single MFBO iteration

- Added `scripts/run_one_optimization_iteration.py` so one ask-evaluate-record
  action can be executed without allowing the continuous engine to schedule the
  next design automatically.
- PI-MFBO trial 6 and standard-MFBO cached trial 5 use the same second coarse
  LHS design. The generated mesh has 1,842,584 cells and minimum orthogonal
  quality `0.04146`. The complete pipeline took about 81.5 minutes.
- The result contract passed: protected eta `0.66861291`, whole-wall eta
  `0.56652452`, coolant mass ratio `0.9999992`, continuity `3.78e-3`, and y+
  p95/max `8.51/12.32`. Pressure-loss ratio `1.1963` remains diagnostic.
- This design is `1.99%` below the coarse baseline and `3.39%` below the current
  best coarse observation. It is retained as a valid negative observation; the
  incumbent remains protected eta `0.69209765` on L2 and `0.65747956` on L3.
- Nominal cumulative costs are now PI-MFBO `2.601` and standard MFBO `2.600`.
  Both methods still propose the same third L2 LHS point. Prior-informed and
  standard acquisitions only begin to diverge after the frozen five-point
  coarse startup has been completed.
- Final record:
  `runs/optimization/nasa_pimfbo/iteration_0006_final_record.json`.

## 2026-07-18 - Eight-dimensional standard-MFBO startup state

- Released the shared downstream-hole diameter and integer spanwise hole count,
  producing the active eight-dimensional design. The complete model contains
  five fixed leading-edge rows plus four parameterized downstream rows
  (`SS1/SS2/PS1/PS2`), not two rows in total.
- Migrated six accepted L2 anchors and three exact paired L3 observations into
  an independent prior-disabled standard-MFBO ledger. The L2 startup target is
  18 designs; 10 L2 and 3 L3 trials are currently complete with no failures.
- Completed the first `N=4/5/6/7` stratified L2 set. Protected eta is
  `0.60550/0.67824/0.71853/0.74902`, compared with the coarse baseline
  `0.68221`. All four pass coolant-flow, continuity, mesh, and y+ screening.
  Other design variables also differ, so the trend is not attributed solely
  to span count or open area.
- Current nominal cost is `5.0/16.5` equivalent L3 evaluations. Eight more L2
  startup cases are required before the first acquisition-driven
  `standard_constrained_ei` proposal. Existing L3 pairs cover only the inherited
  `D=0.99 mm`, `N=5` slice; add at least two released-D/N L3 calibration pairs
  before claiming a robust eight-dimensional fidelity relationship.
- Frozen current status: `docs/project_status.md`. Machine-readable startup
  summary: `runs/optimization/nasa_standard_mfbo_8d/startup_summary/`.
