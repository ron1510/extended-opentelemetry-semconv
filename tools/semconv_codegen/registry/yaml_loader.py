from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml


def load_yaml_document(path: Path) -> dict[str, object]:
    """Parse an OTel model YAML file into raw Python data."""

    data: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping document")
    mapping = cast(dict[object, object], data)
    if not all(isinstance(key, str) for key in mapping):
        raise ValueError(f"{path}: expected string mapping keys")
    return cast(dict[str, object], mapping)
