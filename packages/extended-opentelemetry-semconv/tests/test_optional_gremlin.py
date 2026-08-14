from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_base_package_does_not_import_gremlin_dependency() -> None:
    package_source = Path(__file__).resolve().parents[1] / "src"
    script = """
import builtins

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "gremlin_python" or name.startswith("gremlin_python."):
        raise AssertionError("base semantic package imported gremlin-python")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import extended_otel_semconv
assert extended_otel_semconv.Service.__name__ == "Service"
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(package_source)

    subprocess.run([sys.executable, "-c", script], check=True, env=environment, text=True)
