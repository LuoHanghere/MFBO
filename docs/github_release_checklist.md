# GitHub Release Checklist

## Included

- Python and PowerShell source.
- Unit tests.
- YAML, CSV, workflow, and JSON configuration.
- Markdown documentation and selected configuration figures.
- Compact `runs/**/*.json` geometry, mesh, convergence, postprocessing, and
  optimization provenance records.

## Excluded

- Fluent case, data, and mesh files.
- HDF5, CAD, SAT, Workbench, and SQLite binaries.
- Face-level and volume-level CSV exports outside `configs/`.
- Solver transcripts, logs, cache files, PDFs, and generated Word documents.
- Python environments and local IDE state.

The local `runs/` tree remains the authoritative restart archive. Git contains
only compact machine-readable records and is not a substitute for binary CFD
storage.

## Before Publishing

```powershell
& .\.venv\python.exe -m pytest -q
& .\.venv\python.exe scripts\audit_repository_release.py
git diff --check
git status --short
```

Confirm the following manually:

1. Choose a repository name and public/private visibility.
2. Select an open-source license, or keep the repository private. No license is
   currently granted.
3. Confirm that ANSYS-derived CAD templates may be distributed before adding
   them through Git LFS or a release archive. They are currently excluded.
4. Commit from a `codex/` branch and inspect the GitHub file list before making
   the repository public.
