from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_document(path: Path) -> dict[str, Any]:
    """Parse an OTel model YAML file into raw Python data."""

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping document")
    return data
