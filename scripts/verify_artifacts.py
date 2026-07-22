"""Inspect independently built wheels and emit immutable artifact evidence."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WheelEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project: str
    filename: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    python_modules: tuple[str, ...]
    contains_tests: bool


class ArtifactReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    wheels: tuple[WheelEvidence, ...]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_wheels(args.dist)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report.model_dump_json(indent=2))
    return 0


def inspect_wheels(dist: Path) -> ArtifactReport:
    wheels = tuple(sorted(dist.glob("*.whl")))
    if len(wheels) != 2:
        raise RuntimeError(f"expected exactly two wheels in {dist}, found {[path.name for path in wheels]}")
    evidence = tuple(_inspect_wheel(path) for path in wheels)
    projects = {item.project for item in evidence}
    expected = {"extended-opentelemetry-semconv", "otel-servicegraph-diff"}
    if projects != expected:
        raise RuntimeError(f"unexpected wheel projects: {sorted(projects)}")
    semantic = next(item for item in evidence if item.project == "extended-opentelemetry-semconv")
    application = next(item for item in evidence if item.project == "otel-servicegraph-diff")
    if semantic.python_modules != ("extended_otel_semconv",):
        raise RuntimeError(f"semantic wheel crossed package boundary: {semantic.python_modules}")
    if application.python_modules != ("otel_servicegraph_diff",):
        raise RuntimeError(f"application wheel crossed package boundary: {application.python_modules}")
    if any(item.contains_tests for item in evidence):
        raise RuntimeError("published wheels must not contain tests")
    return ArtifactReport(wheels=evidence)


def _inspect_wheel(path: Path) -> WheelEvidence:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
    project = _metadata_value(metadata, "Name")
    modules = tuple(
        sorted(
            {
                name.partition("/")[0]
                for name in names
                if "/" in name and ".dist-info/" not in name and not name.startswith("__pycache__/")
            }
        )
    )
    return WheelEvidence(
        project=project,
        filename=path.name,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        size_bytes=path.stat().st_size,
        python_modules=modules,
        contains_tests=any(part == "tests" for name in names for part in Path(name).parts),
    )


def _metadata_value(metadata: str, key: str) -> str:
    prefix = f"{key}: "
    value = next((line.removeprefix(prefix) for line in metadata.splitlines() if line.startswith(prefix)), None)
    if value is None:
        raise RuntimeError(f"wheel METADATA has no {key} field")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
