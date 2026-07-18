"""Report whether a clone is ready for tests, Fluent, and full CAD-to-CFD runs."""
from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPORTS = ("numpy", "scipy", "matplotlib", "yaml")


def existing_path(value: str | None) -> bool:
    return bool(value and Path(value).expanduser().exists())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-cfd", action="store_true")
    parser.add_argument("--require-cad", action="store_true")
    args = parser.parse_args()

    missing_imports = [
        name for name in REQUIRED_IMPORTS if importlib.util.find_spec(name) is None
    ]
    compact_inputs = {
        "8D optimizer config": ROOT / "configs/c3x_nasa_standard_mfbo_8d.yaml",
        "base design JSON": Path(
            os.environ.get(
                "BOFM_C3X_BASE_DESIGN",
                ROOT
                / "runs/nasa_44344/geometry/"
                "c3x_nasa44344_periodic_v2_design.json",
            )
        ),
        "boundary targets JSON": Path(
            os.environ.get(
                "BOFM_C3X_BOUNDARY_TARGETS",
                ROOT
                / "runs/workbench/periodic_v2/geometry_freeze/"
                "c3x_boundary_targets.json",
            )
        ),
    }
    ansys_root = os.environ.get("BOFM_ANSYS_ROOT") or os.environ.get("AWP_ROOT242")
    license_server = os.environ.get("ANSYSLMD_LICENSE_FILE") or os.environ.get(
        "BOFM_ANSYS_LICENSE"
    )
    template = os.environ.get(
        "BOFM_C3X_TEMPLATE",
        str(
            ROOT
            / "runs/workbench/periodic_v2/template/"
            "c3x_kumar_fixed_le_template.scdoc"
        ),
    )
    default_spaceclaim = (
        Path(ansys_root) / "scdm" / "SpaceClaim.exe"
        if ansys_root
        else Path(r"D:\Ansys\ANSYS Inc\v242\scdm\SpaceClaim.exe")
    )
    spaceclaim = os.environ.get("BOFM_SPACECLAIM_EXE", str(default_spaceclaim))
    is_windows = platform.system() == "Windows"

    print(f"platform: {platform.platform()}")
    print(f"python: {sys.version.split()[0]}")
    print(f"project: {ROOT}")
    dependency_state = "OK" if not missing_imports else "MISSING " + ", ".join(missing_imports)
    print(f"python dependencies: {dependency_state}")
    for label, path in compact_inputs.items():
        print(f"{label}: {'OK' if path.exists() else 'MISSING'} ({path})")
    print(f"ANSYS root configured: {'YES' if ansys_root else 'NO'}")
    print(f"license configured: {'YES' if license_server else 'NO'}")
    print(
        "external C3X template: "
        f"{'OK' if existing_path(template) else 'MISSING'} ({template})"
    )
    if is_windows:
        print(
            "SpaceClaim executable: "
            f"{'OK' if existing_path(spaceclaim) else 'USE DEFAULT/NOT VERIFIED'}"
        )
    else:
        print("SpaceClaim CAD generation: UNAVAILABLE ON THIS LINUX HOST")

    core_ok = not missing_imports and all(path.exists() for path in compact_inputs.values())
    cfd_ok = core_ok and bool(ansys_root) and bool(license_server)
    cad_ok = cfd_ok and is_windows and existing_path(template)
    if args.require_cfd and not cfd_ok:
        return 2
    if args.require_cad and not cad_ok:
        return 3
    return 0 if core_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
