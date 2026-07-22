"""Verify the semantic wheel has no implicit PyFlink runtime dependency."""

from __future__ import annotations

import importlib.util

import extended_otel_semconv


def main() -> int:
    assert extended_otel_semconv.__name__ == "extended_otel_semconv"
    if importlib.util.find_spec("pyflink") is not None:
        raise RuntimeError("semantic-only environment unexpectedly contains PyFlink")
    print("semantic wheel imports without PyFlink")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
