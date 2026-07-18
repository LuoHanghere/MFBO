# C3X Known Issues (recorded, fix deferred)

## Downstream holes exit plenum when moving s/s0

**Observed:** Parametric moves of SS/PS row `s/s0` (e.g. variant_a vs baseline) can
place cylindrical holes so they **pierce outside the resolved coolant plenum** instead
of staying inside the cavity.

**Status:** Controlled 2026-07-03.  The plenums stay fixed and BO candidates are
rejected before CAD when a full-radius hole does not enter the assigned plenum
with an additional `0.25D` wall margin.

**Implemented controls:**

- Current same-frame plenum polygons:
  `configs/c3x_fixed_downstream_plenums.json`.
- Pre-CAD gate: `scripts/validate_workbench_layout.py`.
- The gate is mandatory inside `scripts/build_c3x_workbench_case.py`; an invalid
  design writes `*_geometry_gate.json` and returns before SpaceClaim starts.
- Conditional baseline-angle range scan:
  `configs/c3x_row_feasible_ranges_baseline_angles.json`.
- Every BO candidate still uses the dynamic gate because the two rows on one
  surface share an injection-axis frame and angle changes alter feasibility.
- Plenum resizing/motion is intentionally deferred: changing coolant-domain
  geometry between BO samples would introduce an additional uncontrolled design
  change.

## SAT / headless PyFluent mesh loses boundary names

**Observed:** SpaceClaim face labels (`qian`, `ss`, `inlet`, …) do not survive
`.sat` export. PyFluent watertight meshing merges external faces to a single wall
zone; `split_merged_boundary(1°)` explodes into 10k+ zones on film-cooled geometry.

**Policy:** On the primary dev machine, **mesh only via Workbench Discovery → Fluent
Meshing**. Do not use SAT or split for solver prep. See `docs/c3x_workbench_route.md`.

## Fine-grid memory and solution interpolation

**Observed:** The `6,433,128`-cell NASA fine mesh exceeds practical memory for
16-core setup/partitioning on the current 32 GB workstation. Setup succeeds at
four cores and solution continuation is stable at eight cores.

Fluent 24.2 `mesh.replace` solution interpolation from the 3.78M paper mesh to
the 6.43M fine mesh failed: 16 cores exhausted memory and four cores reached a
Fluent segmentation fault during cell interpolation.

**Policy:** Use four cores for fine setup, eight for the fine solve, and start
the fine solution normally. Do not rely on cross-mesh `mesh.replace` in the
automated pipeline unless it is independently reproduced on a higher-memory
machine.
