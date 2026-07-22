"""Render third-party runtime dependencies from package metadata."""

from __future__ import annotations

import argparse
import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PROJECT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pyprojects", nargs="+", type=Path)
    parser.add_argument("--exclude-project", action="append", default=[])
    args = parser.parse_args()

    excluded = {_normalized_name(name) for name in args.exclude_project}
    for dependency in runtime_dependencies(args.pyprojects, excluded):
        print(dependency)
    return 0


def runtime_dependencies(pyprojects: Iterable[Path], excluded: set[str]) -> tuple[str, ...]:
    dependencies: dict[str, str] = {}
    for pyproject in pyprojects:
        document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = _mapping(document.get("project"), pyproject)
        raw_dependencies = project.get("dependencies", [])
        if not isinstance(raw_dependencies, list) or not all(
            isinstance(dependency, str) for dependency in raw_dependencies
        ):
            raise ValueError(f"{pyproject}: project.dependencies must be a list of strings")
        for dependency in raw_dependencies:
            name = _dependency_name(dependency, pyproject)
            if name in excluded:
                continue
            previous = dependencies.setdefault(name, dependency)
            if previous != dependency:
                raise ValueError(
                    f"conflicting requirements for {name}: {previous!r} and {dependency!r}"
                )
    return tuple(dependencies[name] for name in sorted(dependencies))


def _mapping(value: Any, source: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{source}: missing project table")
    return value


def _dependency_name(requirement: str, source: Path) -> str:
    match = PROJECT_NAME.match(requirement)
    if match is None:
        raise ValueError(f"{source}: invalid dependency {requirement!r}")
    return _normalized_name(match.group(1))


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


if __name__ == "__main__":
    raise SystemExit(main())
