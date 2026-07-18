$ErrorActionPreference = "Stop"

$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $Python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe scripts\check_server_readiness.py
& .\.venv\Scripts\python.exe -m pytest -q
