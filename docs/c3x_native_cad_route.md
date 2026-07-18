# C3X Route A — native CAD directly into Fluent Meshing

## Status

Validated on 2026-07-03 with Fluent 2024 R2 / PyFluent 0.20.0.  Fluent Meshing
can now read the native baseline SCDOC headlessly.  Workbench and SAT are not
required for the geometry-to-mesh step.

## Production path

```text
design JSON
  -> resolve row positions/angles and cylinder markers
  -> mandatory fixed-plenum geometry gate (radius + 0.25D margin)
  -> SpaceClaim journal builds one-body SCDOC with face named selections
  -> headless Fluent Meshing imports SCDOC
  -> surface mesh
  -> fluid-only topology description
  -> pressure-inlet boundary typing
  -> scoped prism boundary layers
  -> polyhedral volume mesh
  -> normalize CAD-derived zone suffixes
  -> MSH.H5
  -> NASA setup / iterate / export / manifest
```

Geometry generation is unchanged:

```powershell
& .\.venv\python.exe scripts\run_workbench_case.py --name baseline
```

Before SpaceClaim starts, the builder writes `*_geometry_gate.json`.  Invalid
BO candidates stop here and must not be meshed.  The gate uses
`configs/c3x_fixed_downstream_plenums.json` in the current CAD coordinate frame.

Despite the historical command name, this produces the native SCDOC needed by
Route A.  Direct meshing is:

```powershell
& .\.venv\python.exe scripts\run_fluent_native_cad_mesh.py `
  --cad runs\workbench\baseline\c3x_wb_baseline.scdoc `
  --tier smoke --cores 8
```

## Required import behavior

- `UseBodyLabels=Yes` is required for reliable direct SCDOC attachment on this
  machine.  A controlled `UseBodyLabels=No` test failed in PartMgr
  `AttachAssembly()` after about 121 seconds.
- `ImportNamedSelections=True` and `ImportPartNames=True` preserve the CAD face
  selections.
- CAD length unit is `m`; the imported bounding box is approximately
  `[-0.117, -0.305, 0]` to `[0.156, 0.170, 0.01485] m`.
- Body-label suffixes are normalized only after the polyhedral mesh has merged
  to one fluid cell zone.

## Validated smoke result

Input: `runs/workbench/baseline/c3x_wb_baseline.scdoc`

- 8 Fluent processes
- surface size: `0.12–4.0 mm`, growth `1.2`
- 8 prism layers, requested first height `0.020 mm`, growth `1.2`
- volume fill: `polyhedra`
- cells: `915,204` (corrected large-side coolant inlets)
- surface maximum skewness: `0.7840`
- minimum volume orthogonal quality: `0.08331`
- final fluid cell zones: `1`
- elapsed mesh run: about `86 s`

Retained validated mesh:

- `runs/direct_cad/smoke/baseline_native_final.msh.h5`
- `runs/direct_cad/smoke/baseline_native_final_zones.json`

Final boundary zones are unique and solver-ready:

- `inlet`, `outlet`
- `qian`, `ss`, `ps`
- `periodic_low`, `periodic_high`
- `span_low`, `span_high`
- `vane_wall`, `film_hole_wall`, `plenum_wall`

## Current decisions and caveats

- Use `polyhedra` as the first Route-A production fill.  The tested
  `poly-hexcore` path retained separate prism/core cell zones and split boundary
  pieces such as `qian-quad`; production is now locked to `polyhedra`.
- The successful run proves direct CAD import, boundary-layer creation, volume
  meshing, and name preservation.  It does not yet prove first-height
  sensitivity or grid independence.
- No solver iteration was run during this validation.
- Workbench Route B remains a fallback until Route A completes topology check,
  solver setup, and coarse/paper/fine grid-independence runs.

## Standardized production artifacts

For every design `<name>`, retain:

1. `c3x_wb_<name>_design.json` — resolved BO variables.
2. `c3x_wb_<name>_layout.json/.csv/.png` — hole construction and visual check.
3. `c3x_wb_<name>_geometry_gate.json` — pre-CAD feasibility decision.
4. `c3x_wb_<name>.scdoc` — one connected fluid body with named faces.
5. `<name>_<tier>.msh.h5` plus mesh metadata — native-CAD polyhedral mesh.
6. topology/setup/iteration/post-processing JSON and case/data files.
7. final run manifest consumed by the grid-independence and BO summaries.

Boundary naming is fixed as:

- mainstream: `inlet`, `outlet`;
- coolant supplies: `qian` (LE), `ss`, `ps`;
- periodic pairs: `periodic_low/high`, `span_low/high`;
- walls: `vane_wall`, `film_hole_wall`, `plenum_wall` after mesh normalization.
