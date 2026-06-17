"""CPython-side driver that runs an IronPython journal inside SpaceClaim.

SpaceClaim is launched headless in batch mode (/RunScript). Headless SpaceClaim
does not reliably surface Python errors on stdout, so the journal writes a
status file (BOFM_STATUS) with 'OK' or a traceback; this driver reads it back to
decide success/failure.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

SPACECLAIM_EXE = r"D:\Ansys\ANSYS Inc\v242\scdm\SpaceClaim.exe"


@dataclass
class JournalResult:
    returncode: int
    status: str            # 'OK' or traceback text or '<no status file>'
    status_path: Path
    out_scdoc: Path | None
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.status.strip().startswith("OK")


def run_journal(journal: str | Path,
                placements_json: str | Path | None = None,
                out_scdoc: str | Path | None = None,
                *,
                env_extra: dict[str, str] | None = None,
                spaceclaim_exe: str | Path = SPACECLAIM_EXE,
                headless: bool = True,
                timeout_s: int = 600) -> JournalResult:
    """Run `journal` inside SpaceClaim, passing paths to it via env vars.

    `env_extra` lets callers hand the journal arbitrary BOFM_* inputs (e.g.
    BOFM_PASSAGE_JSON); values are stringified and resolved if they are paths.
    """
    journal = Path(journal).resolve()
    status_path = journal.with_suffix(".status.txt")
    if status_path.exists():
        status_path.unlink()

    env = os.environ.copy()
    env["BOFM_STATUS"] = str(status_path)
    for k, v in (env_extra or {}).items():
        env[k] = str(v)
    if placements_json:
        env["BOFM_PLACEMENTS_JSON"] = str(Path(placements_json).resolve())
    if out_scdoc:
        out_scdoc = Path(out_scdoc).resolve()
        out_scdoc.parent.mkdir(parents=True, exist_ok=True)
        env["BOFM_OUT_SCDOC"] = str(out_scdoc)

    cmd = [str(spaceclaim_exe), f"/RunScript={journal}",
           "/Splash=False", "/ExitAfterScript=True", "/ScriptAPI=242"]
    if headless:
        cmd.insert(2, "/Headless=True")

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                          timeout=timeout_s)
    status = status_path.read_text(encoding="utf-8") if status_path.exists() \
        else "<no status file>"
    return JournalResult(proc.returncode, status, status_path,
                         Path(out_scdoc) if out_scdoc else None,
                         proc.stdout, proc.stderr)
