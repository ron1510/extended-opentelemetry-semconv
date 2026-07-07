from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from extended_otel_semconv.upstream.drift import compare_model_dirs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two local OTel model snapshots without network access.")
    parser.add_argument("old_model_dir", type=Path, help="Old model directory containing <domain>/registry.yaml")
    parser.add_argument("new_model_dir", type=Path, help="New model directory containing <domain>/registry.yaml")
    parser.add_argument("--domain", default="k8s", help="Model domain to compare")
    args = parser.parse_args()

    report = compare_model_dirs(args.old_model_dir, args.new_model_dir, args.domain)
    for line in report.lines():
        print(line)
    return 1 if report.has_changes else 0


if __name__ == "__main__":
    raise SystemExit(main())
