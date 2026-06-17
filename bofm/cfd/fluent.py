"""Centralized Fluent 2024R2 launch for the BOfm pipeline.

Validated 2026-06: PyFluent 0.20.0 launches local Fluent 2024R2 (FluentVersion.v242),
license 1055@localhost, headless. Everything runs from the project folder; the
python env lives in .venv to avoid the non-ASCII user-profile path.

NOTE on AWP root: there are two v242 trees on this machine —
  - D:\Ansys\v242              -> SCDM/Motion only (NO solver)   <-- do NOT use
  - D:\Ansys\ANSYS Inc\v242    -> full install incl. fluent\     <-- use this
The path has a space but no non-ASCII characters, which keeps Fluent happy.
"""
import os

AWP_ROOT_242 = r"D:\Ansys\ANSYS Inc\v242"
LICENSE = "1055@localhost"


def ensure_env() -> None:
    """Point PyFluent at the real local Fluent 2024R2 install + license."""
    os.environ.setdefault("AWP_ROOT242", AWP_ROOT_242)
    os.environ.setdefault("ANSYSLMD_LICENSE_FILE", LICENSE)


def launch(mode: str = "solver", processor_count: int = 1,
           ui_mode: str = "no_gui", start_timeout: int = 300, **kwargs):
    """Launch Fluent with project defaults. mode = 'meshing' | 'solver'.

    start_timeout defaults to 300 s: multi-core MPI meshing startup on this
    laptop can take >60 s, and the 0.20.0 default times out the gRPC connect.
    """
    ensure_env()
    import ansys.fluent.core as pf
    return pf.launch_fluent(mode=mode, processor_count=processor_count,
                            ui_mode=ui_mode, start_timeout=start_timeout,
                            **kwargs)
