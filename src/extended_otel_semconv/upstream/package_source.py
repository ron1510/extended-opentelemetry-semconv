from __future__ import annotations

from importlib import metadata

from pydantic import BaseModel, ConfigDict, computed_field


class SemconvPackageInspection(BaseModel):
    model_config = ConfigDict(frozen=True)

    package: str
    version: str
    yaml_files: tuple[str, ...]

    @computed_field
    @property
    def exposes_model_yaml(self) -> bool:
        return bool(self.yaml_files)


def inspect_semconv_package(package: str = "opentelemetry-semantic-conventions") -> SemconvPackageInspection:
    files = tuple(str(file) for file in (metadata.files(package) or ()))
    yaml_files = tuple(sorted(file for file in files if file.endswith((".yaml", ".yml"))))
    return SemconvPackageInspection(package=package, version=metadata.version(package), yaml_files=yaml_files)
