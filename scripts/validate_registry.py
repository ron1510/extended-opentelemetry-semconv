from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from extended_otel_semconv.registry.validation import validate_model_files  # noqa: E402


def main() -> int:
    validate_model_files(ROOT / "model" / "k8s" / "registry.yaml", ROOT / "model" / "k8s" / "entities.yaml")
    print("OTel-style registry validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
