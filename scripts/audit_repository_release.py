"""Audit the files that would be included in a Git repository snapshot."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


FORBIDDEN_SUFFIXES = (
    ".cas",
    ".cas.h5",
    ".dat",
    ".dat.h5",
    ".msh",
    ".msh.h5",
    ".scdoc",
    ".pmdb",
    ".sat",
    ".trn",
    ".wbpj",
    ".sqlite",
    ".sqlite3",
)
ALLOWED_BINARY_PATHS = {
    Path(
        "runs/workbench/periodic_v2/template/"
        "c3x_kumar_fixed_le_template.scdoc"
    )
}
MAX_FILE_BYTES = 10 * 1024 * 1024
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"(?:password|passwd|api[_-]?key|secret|access[_-]?token)"
        r"\s*[=:]\s*['\"]?[^\s,'\"]{8,}",
        re.IGNORECASE,
    ),
)


def repository_paths() -> list[Path]:
    output = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ]
    )
    return [Path(raw.decode("utf-8")) for raw in output.split(b"\0") if raw]


def main() -> int:
    paths = [path for path in repository_paths() if path.is_file()]
    failures: list[str] = []
    json_count = 0
    total_bytes = 0

    for path in paths:
        size = path.stat().st_size
        total_bytes += size
        lowered = path.name.lower()
        if (
            lowered.endswith(FORBIDDEN_SUFFIXES)
            and path not in ALLOWED_BINARY_PATHS
        ):
            failures.append(f"forbidden solver artifact: {path}")
        if size > MAX_FILE_BYTES:
            failures.append(f"file exceeds 10 MiB: {path} ({size} bytes)")
        if path.suffix.lower() == ".json":
            json_count += 1
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(f"invalid JSON: {path}: {exc}")
        if path.suffix.lower() in {".py", ".ps1", ".md", ".yaml", ".yml", ".json"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                failures.append(f"non-UTF-8 text file: {path}")
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    failures.append(
                        f"possible credential ({pattern.pattern}): {path}"
                    )

    print(f"release files: {len(paths)}")
    print(f"release size: {total_bytes / 1024 / 1024:.2f} MiB")
    print(f"JSON records: {json_count}")
    if failures:
        print("release audit failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("release audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
