"""Compatibility entrypoint for the validating confidence load stage."""

from __future__ import annotations

from extended_otel_semconv_devtools.confidence.scale import main

if __name__ == "__main__":
    raise SystemExit(main())
