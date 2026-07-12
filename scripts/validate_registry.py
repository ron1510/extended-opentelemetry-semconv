from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from extended_otel_semconv.registry.validation import validate_extension_model  # noqa: E402


def main() -> int:
    validate_extension_model(
        ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model",
        ROOT / "model" / "extensions",
    )
    print("OTel extension registry validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
