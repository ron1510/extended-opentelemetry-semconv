from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("powershell") is None, reason="PowerShell is unavailable")
@pytest.mark.parametrize(
    "script",
    [
        "build_wheels.ps1",
        "run_confidence.ps1",
        "smoke_compose.ps1",
    ],
)
def test_powershell_script_parses(script: str) -> None:
    path = ROOT / "scripts" / script
    command = (
        "$errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$null, [ref]$errors) | Out-Null; "
        "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )

    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )
