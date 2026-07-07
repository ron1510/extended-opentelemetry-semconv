from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from extended_otel_semconv.upstream.package_source import inspect_semconv_package  # noqa: E402


def main() -> int:
    inspection = inspect_semconv_package()
    print(f"{inspection.package}=={inspection.version}")
    if inspection.exposes_model_yaml:
        print("model YAML files:")
        for path in inspection.yaml_files:
            print(path)
    else:
        print("model YAML files: none; package exposes generated constants only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
