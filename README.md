# BOfm

BOfm is a research codebase for automated C3X turbine-vane film-cooling
geometry, CFD evaluation, and multi-fidelity Bayesian optimization (MFBO).
The current production problem maximizes protected-area adiabatic
film-cooling effectiveness using coarse and paper-grade Fluent meshes.

## Current Model

- Five fixed NASA leading-edge cooling rows.
- Four parameterized downstream rows: `SS1`, `SS2`, `PS1`, and `PS2`.
- Eight optimization variables: four row positions, suction/pressure injection
  angles, shared hole diameter, and integer spanwise hole count.
- L2: coarse CFD, relative cost `0.20`.
- L3: paper-grid CFD, relative cost `1.00`.
- Fine CFD is reserved for independent finalist audits.

The standard-MFBO configuration has its physics prior disabled. The proposed
PI-MFBO will use the same CFD data and budget with a separately frozen L1
knowledge model.

## Production Loop

```text
8D design
  -> geometry feasibility gate
  -> SpaceClaim SCDOC generation
  -> native-CAD Fluent meshing
  -> NASA boundary conditions and solve
  -> result contract and projection figures
  -> SQLite experiment ledger
  -> cost-aware constrained acquisition
```

Primary entry points:

```powershell
# Execute exactly one ask-evaluate-record step.
& .\.venv\python.exe scripts\run_one_optimization_iteration.py `
  --config configs\c3x_nasa_standard_mfbo_8d.yaml

# Finish startup sampling and continue into acquisition-driven standard MFBO.
& .\.venv\python.exe scripts\run_standard_mfbo_cycle.py `
  --config configs\c3x_nasa_standard_mfbo_8d.yaml `
  --bo-iterations 1

# Start the local experiment monitor.
& .\.venv\python.exe scripts\run_optimization_ui.py `
  --config configs\c3x_nasa_standard_mfbo_8d.yaml
```

## Repository Layout

```text
bofm/          Geometry, CFD, Workbench, and optimization libraries
configs/       Frozen model, mesh, validation, and optimizer configuration
docs/          Method decisions, validation records, and current project status
scripts/       Reproducible command-line workflows
tests/         Unit and contract tests
runs/          Local CFD artifacts; Git keeps JSON records only
```

See [project status](docs/project_status.md) for the current numerical results
and remaining MFBO startup work. The benchmark protocol is documented in
[c3x_optimization_benchmark_protocol.md](docs/c3x_optimization_benchmark_protocol.md).
For a new workstation or server, follow [server migration](docs/server_migration.md)
and let Codex read the root [AGENTS.md](AGENTS.md) first.

## Environment

- Windows and PowerShell
- Python 3.11 environment from `environment.yml` or `requirements.txt`
- ANSYS/Fluent 2024 R2 for production CFD
- A local fixed-leading-edge SCDOC template (large CAD binaries are not stored
  in Git)

```powershell
conda env create --prefix .venv -f environment.yml
& .\.venv\python.exe -m pytest -q
```

## Data Policy

Fluent case/data/mesh files, CAD binaries, Workbench projects, transcripts,
SQLite ledgers, and large CSV exports remain local. Small JSON manifests and
result summaries under `runs/` are retained in Git for provenance. Recreating
CFD cases requires the external SCDOC template and an ANSYS installation.

No public-use license has been selected yet.
