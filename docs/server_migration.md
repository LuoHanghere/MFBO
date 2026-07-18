# Server Migration

## 1. Clone and Bootstrap

```bash
git clone git@github.com:LuoHanghere/MFBO.git
cd MFBO
bash scripts/bootstrap_server.sh
```

On a Windows server:

```powershell
git clone git@github.com:LuoHanghere/MFBO.git
Set-Location MFBO
& .\scripts\bootstrap_server.ps1
```

Codex should read the root `AGENTS.md` before continuing work. The current
research snapshot is in `docs/project_status.md`.

## 2. Configure ANSYS

Copy `.env.example` values into the server shell profile, scheduler job, or a
private environment file that is not committed.

Linux example:

```bash
export BOFM_ANSYS_ROOT=/ansys_inc/v242
export ANSYSLMD_LICENSE_FILE=1055@license-server
export BOFM_C3X_TEMPLATE=/srv/bofm-assets/c3x_kumar_fixed_le_template.scdoc
```

Windows example:

```powershell
$env:BOFM_ANSYS_ROOT = "D:\Ansys\ANSYS Inc\v242"
$env:ANSYSLMD_LICENSE_FILE = "1055@license-server"
$env:BOFM_SPACECLAIM_EXE = "D:\Ansys\ANSYS Inc\v242\scdm\SpaceClaim.exe"
$env:BOFM_C3X_TEMPLATE = "D:\bofm-assets\c3x_kumar_fixed_le_template.scdoc"
```

Verify before releasing CFD:

```bash
.venv/bin/python scripts/check_server_readiness.py --require-cfd
```

Use `--require-cad` only on the Windows CAD node.

## 3. Transfer External Artifacts

Git intentionally excludes large and proprietary solver artifacts. Transfer
these separately with `rsync`, `scp`, or managed research storage:

1. Required for new geometry: the fixed-leading-edge template
   `c3x_kumar_fixed_le_template.scdoc`.
2. Required to resume optimization exactly: the standard-MFBO SQLite ledger
   `runs/optimization/nasa_standard_mfbo_8d/c3x_nasa_standard_mfbo_8d.sqlite3`.
3. Recommended for restart/review: completed trial directories containing
   `.cas.h5`, `.dat.h5`, meshes, transcripts, and postprocessing CSV files.

Do not place these files in Git. Preserve the same paths under `runs/`, or set
the environment overrides for the template and compact geometry inputs.

Example data transfer from the current workstation:

```bash
rsync -av --info=progress2 \
  runs/optimization/nasa_standard_mfbo_8d/ \
  user@server:/work/MFBO/runs/optimization/nasa_standard_mfbo_8d/
```

## 4. Platform Limitation

The current parameterized SCDOC generation calls SpaceClaim and therefore
requires Windows. A Linux server can run the optimizer, tests, result analysis,
and supported Fluent operations, but cannot currently create a new SCDOC from
the 8D design by itself. Use one of these deployment patterns:

- Run the complete loop on a Windows ANSYS server.
- Keep a Windows CAD worker that writes SCDOC files to shared storage, then run
  meshing/solve/postprocessing on Linux.
- Pre-generate a design batch on Windows before submitting Linux CFD jobs.

Treat full Linux CAD-to-CFD automation as a future portability task, not as a
currently validated capability.

## 5. Resume Checklist

1. `git status` is clean and the expected branch is checked out.
2. `scripts/check_server_readiness.py` passes at the required level.
3. `python -m pytest -q` reports the expected passing test count.
4. The transferred SQLite ledger reports 10 L2 and 3 L3 completed trials at the
   2026-07-18 snapshot.
5. The external SCDOC template checksum matches the workstation copy.
6. Run one dry/read-only policy inspection before releasing the next L2 trial.
