# Workbench mesh tiers for C3X Route B

Route B uses Workbench/Discovery/Fluent Meshing because this workstation must
preserve named boundaries from SCDOC. The preferred direction is now automated
Workbench batch meshing through `scripts/run_workbench_mesh_tier.py`, followed
by solver setup through `scripts/run_workbench_validation_pipeline.py`.

Current automation status:

- Workbench batch control works through `RunWB2 -B -F 1.wbpj -R <journal>`.
- Fluent Meshing can import the Discovery `.dsco`, generate surface/volume mesh,
  and write `.msh.h5` via `meshing.File.WriteMesh(FileName=...)`.
- Fluent solver can read the generated `.msh.h5`; named zones are preserved and
  the setup script creates the pitch/span periodic pairs.
- Boundary-layer task control now has a working batch route for the current
  Workbench project: update the existing `smooth-transition_1` compound child
  instead of trying to add another child. Production `coarse/paper/fine` meshes
  still require one additional verification step: confirm that changing tier
  layer count/first height changes the generated volume mesh, not just the
  saved workflow arguments.

## Baseline geometry prerequisite

Use the current baseline layout:

- design: `runs/workbench/baseline/c3x_wb_baseline_design.json`
- layout: `runs/workbench/baseline/c3x_wb_baseline_layout.json`
- SCDOC: `runs/workbench/baseline/c3x_wb_baseline.scdoc`

Before meshing:

```powershell
& .\.venv\python.exe scripts\validate_workbench_layout.py `
  --layout runs\workbench\baseline\c3x_wb_baseline_layout.json `
  --out-json runs\workbench\baseline\c3x_wb_baseline_topology_check_no_cavities.json
```

## Tier settings

The source of truth is `configs/c3x_mesh_tiers.yaml`.

| Tier | Purpose | Surface Min/Max [mm] | Growth | Prism layers | First layer [mm] | Prism growth | Expected cells |
|---|---|---:|---:|---:|---:|---:|---:|
| `coarse` | BO screening | 0.06 / 2.0 | 1.18 | 15 | 0.005 | 1.18 | 1.5-3.0M |
| `paper` | paper working grid | 0.04 / 1.5 | 1.15 | 25 | 0.002 | 1.18 | 3.0-5.0M |
| `fine` | grid-convergence upper level | 0.03 / 1.0 | 1.12 | 30 | 0.0005 | 1.16 | 6.0-10.0M |

The previous baseline `startup100` result is a `smoke`-level pipeline check, not
a paper-quality mesh.

## Automated Workbench mesh generation

Debug/smoke command, no boundary layers:

```powershell
& .\.venv\python.exe scripts\run_workbench_mesh_tier.py `
  --tier smoke `
  --name baseline_smoke_writeprobe `
  --out-mesh runs\workbench\grid_independence\smoke_probe\baseline_smoke_writeprobe_mesh.msh.h5 `
  --skip-boundary-layers
```

Production command template, after the final volume-mesh sensitivity check:

```powershell
& .\.venv\python.exe scripts\run_workbench_mesh_tier.py `
  --tier coarse `
  --name baseline_coarse `
  --out-mesh runs\workbench\grid_independence\coarse\baseline_coarse_mesh.msh.h5
```

Implementation note:

- `workflow.TaskObject['Add Boundary Layers'].AddChildAndUpdate(...)` fails in
  this project because a child control already exists.
- The script therefore updates
  `workflow.TaskObject['smooth-transition_1'].Arguments` and executes that
  existing child.
- The workflow file should be checked after each tier to confirm
  `NumberOfLayers`, `FirstHeight`, `Rate`, and
  `LocalPrismPreferences.IgnoreBoundaryLayers = no`.

Expected automated mesh files:

```text
runs/workbench/grid_independence/coarse/baseline_coarse_mesh.msh.h5
runs/workbench/grid_independence/paper/baseline_paper_mesh.msh.h5
runs/workbench/grid_independence/fine/baseline_fine_mesh.msh.h5
```

## Workbench GUI fallback convention

For each tier:

1. Open `1.wbpj`.
2. Replace/update Discovery geometry with the baseline SCDOC if needed.
3. In Fluent Meshing:
   - units: meters;
   - `UseBodyLabels = Yes`;
   - fluid-only geometry, no voids;
   - apply the tier-specific surface sizing and prism-layer settings;
   - use polyhedra volume fill for every Route-A tier;
   - update `qian`, `ss`, and `ps` to pressure-inlet if Workbench labels them
     incorrectly.
4. Write the mesh/case to:

```text
runs/workbench/grid_independence/<tier>/baseline_<tier>_mesh.msh.h5
```

Expected files:

```text
runs/workbench/grid_independence/coarse/baseline_coarse_mesh.msh.h5
runs/workbench/grid_independence/paper/baseline_paper_mesh.msh.h5
runs/workbench/grid_independence/fine/baseline_fine_mesh.msh.h5
```

## Automated pipeline after mesh export

After Workbench writes a tier mesh:

```powershell
& .\.venv\python.exe scripts\run_workbench_validation_pipeline.py `
  --name baseline_coarse `
  --tier coarse `
  --case-in runs\workbench\grid_independence\coarse\baseline_coarse_mesh.msh.h5 `
  --iters 1000 `
  --cores 16 `
  --precision single
```

Repeat with `paper` and `fine`.

The pipeline performs:

```text
topology check -> setup -> iterate -> export -> manifest
```

Outputs per tier include:

```text
baseline_<tier>_topology_check.json
baseline_<tier>_mesh_meta.json
baseline_<tier>_setup.cas.h5
baseline_<tier>_iter1000.cas.h5
baseline_<tier>_iter1000.dat.h5
post_iter1000/bo_summary.json
baseline_<tier>_iter1000_manifest.json
```

## Grid-independence summary

After at least two tier manifests exist:

```powershell
& .\.venv\python.exe scripts\summarize_workbench_grid_independence.py
```

This writes:

```text
runs/workbench/grid_independence/grid_independence_summary.csv
runs/workbench/grid_independence/grid_independence_summary.md
```

Decision rule:

- use `coarse` for BO only if it tracks `paper` trends and constraints reliably;
- use `paper` for final optimization/reporting unless `paper -> fine` changes are
  above the thresholds in `docs/c3x_nasa_validation_protocol.md`;
- treat `fine` as the convergence reference, not the default BO fidelity.
