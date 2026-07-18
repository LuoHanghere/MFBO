# Codex Working Guide

## Objective

Continue the C3X eight-dimensional standard-MFBO and PI-MFBO research workflow.
Read `docs/project_status.md` and
`docs/c3x_optimization_benchmark_protocol.md` before changing optimization
logic, fidelity definitions, objectives, or budgets.

## Current State

- Geometry: five fixed leading-edge rows plus four parameterized downstream
  rows (`SS1`, `SS2`, `PS1`, `PS2`).
- Variables: four row positions, two injection angles, shared diameter, and
  integer spanwise hole count.
- L2 is coarse CFD; L3 is paper-grid CFD; fine CFD is audit-only.
- Standard-MFBO prior is disabled.
- Ledger at the 2026-07-18 snapshot: 10 L2 and 3 L3 completed, no failures,
  cost `5.0/16.5`. Eight L2 startup designs remain before the first
  acquisition-driven `standard_constrained_ei` proposal.

The SQLite ledger and large CFD restart files are local artifacts and are not
stored in Git. Compact JSON records under `runs/` are versioned.

## First Commands

```powershell
& .\.venv\python.exe scripts\check_server_readiness.py
& .\.venv\python.exe -m pytest -q
& .\.venv\python.exe scripts\audit_repository_release.py
```

On Linux, use `.venv/bin/python` instead.

## Production Commands

```powershell
# Execute one ask-evaluate-record action.
& .\.venv\python.exe scripts\run_one_optimization_iteration.py `
  --config configs\c3x_nasa_standard_mfbo_8d.yaml

# Finish startup and stop after the requested number of acquisition steps.
& .\.venv\python.exe scripts\run_standard_mfbo_cycle.py `
  --config configs\c3x_nasa_standard_mfbo_8d.yaml `
  --bo-iterations 1
```

Do not run a large batch before verifying the ANSYS license, external SCDOC
template, CPU allocation, and available storage.

## Platform Boundary

Dynamic SCDOC generation currently requires Windows SpaceClaim. Linux supports
tests, optimization logic, postprocessing, and Fluent operations available in
that installation, but the full geometry loop needs either a Windows CAD node
or pre-generated SCDOC cases. Do not claim Linux end-to-end support until this
boundary is removed and tested.

## Repository Rules

- Never commit `.cas/.dat/.msh/.h5/.scdoc/.sqlite/.trn` files.
- Keep small JSON provenance records.
- Do not delete or overwrite local `runs/` restart data without explicit user
  approval.
- Preserve fixed seeds, initial data, budgets, and fidelity costs across method
  comparisons.
- Keep pressure loss diagnostic until its L2/L3 definition is frozen.
- Run all tests and `scripts/audit_repository_release.py` before publishing.
