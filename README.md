# BOfm - turbine-vane film-cooling BO sandbox

This repository is the working codebase for the first paper: a
physics-prior, multi-fidelity Bayesian optimization workflow for C3X turbine
vane film cooling. The current priority is the no-film validation case: make
the clean C3X vane simulation repeatable, compare it with experimental data,
then add film holes.

## What works now

- C3X profile parsing, arc-length parametrization, and baseline hole-placement
  checks.
- Single-pitch periodic passage generation for the no-film validation domain.
- Headless SpaceClaim build of the no-film fluid domain and ACIS `.sat` export.
- Headless Fluent Meshing import, zone classification, surface meshing, prism
  layers, and poly-hexcore volume meshing.
- Headless Fluent setup for compressible SST/ideal-gas no-film flow:
  pressure inlet, pressure outlet, span symmetry, and two non-conformal
  translational periodic interfaces.
- Coarse and refined no-film runs through 200 iterations.
- ParaView-oriented EnSight Gold export plus wall y+ JSON/CSV summaries.

## Current domain choice

The downstream periodic boundaries are inclined with the nominal exit flow
angle rather than forced horizontal. These are pitchwise periodic boundaries,
not measured wake traces, so aligning them with the expected outlet direction
keeps the downstream passage consistent with the cascade periodicity.

The stable baseline keeps the downstream extension at `1.0 Cax`. A `1.5 Cax`
trial built and meshed, but its short solve showed severe inlet/outlet reversed
flow and unstable residual behavior. Keep longer outlets as later
domain-length sensitivity tests, not the main validation path.

## Main commands

Run from the repository root with the project environment:

```powershell
& .\.venv\python.exe scripts\check_parametrization.py
& .\.venv\python.exe scripts\check_passage.py
& .\.venv\python.exe scripts\build_nofilm_domain.py
& .\.venv\python.exe scripts\build_nofilm_mesh.py --tier coarse --cores 4
& .\.venv\python.exe scripts\build_nofilm_mesh.py --tier refined --cores 1
& .\.venv\python.exe scripts\run_nofilm_setup.py --case-in runs\fluid\c3x_nofilm_refined.cas.h5 --split-case runs\fluid\c3x_nofilm_refined_split.cas.h5 --case-out runs\fluid\c3x_nofilm_refined_setup.cas.h5 --cores 4
& .\.venv\python.exe scripts\run_nofilm_iterate.py --case runs\fluid\c3x_nofilm_refined_setup.cas.h5 --iters 200 --out-prefix runs\fluid\c3x_nofilm_refined_run200
& .\.venv\python.exe scripts\export_nofilm_results.py --case runs\fluid\c3x_nofilm_refined_run200.cas.h5 --data runs\fluid\c3x_nofilm_refined_run200.dat.h5
```

Open the EnSight Gold `.case` file written under
`runs/fluid/paraview/c3x_nofilm_refined_run200/` in ParaView. The Fluent
`.cas.h5/.dat.h5` files are also kept in `runs/fluid/` for restart and review.

## Latest no-film refined smoke result

The refined mesh run at 200 iterations is stable enough for workflow
validation:

- mesh: 14,108 cells, 88,576 faces, 67,174 nodes
- iteration 200 residuals: continuity about `1.0e-2`, momentum about `1e-6`,
  energy about `4e-6`, turbulence about `1e-4`
- outlet reversed flow: 2 faces, about `0.8%` of pressure-outlet area

This is not yet the final validation result. The wall is currently adiabatic,
so heat-transfer-coefficient alignment against the experiments still needs the
proper wall thermal condition and extracted comparison stations.

## Repository layout

```text
configs/       C3X baseline data and generated passage/placement checks
bofm/geometry/ Profile parametrization and passage construction
bofm/cad/      SpaceClaim launcher and journals
bofm/cfd/      Fluent launch, meshing, and no-film setup helpers
scripts/       Repeatable check/build/run/export entry points
runs/          Generated CFD artifacts, ignored by git
```

## Local setup

Fluent 2024R2 is expected at `D:\Ansys\ANSYS Inc\v242`, with license
`1055@localhost`. The project Python environment lives in `.venv`.

```powershell
conda env create --prefix .venv -f environment.yml
& .\.venv\python.exe your_script.py
```

## Next work

1. Export and inspect y+ and flow fields in ParaView for the refined run.
2. Add experimental comparison scripts for exit Mach/pressure and, after wall
   thermal setup is corrected, HTC.
3. Run a mesh sensitivity sequence once the comparison metrics are automated.
4. Add film-hole CAD/mesh/solve workflow after the clean-vane validation is
   trustworthy.
