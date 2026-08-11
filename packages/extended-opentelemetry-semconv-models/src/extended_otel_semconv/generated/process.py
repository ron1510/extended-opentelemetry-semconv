from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    bool_value,
    int_value,
    object_value,
    string_value,
)

class Process(SemanticEntity):
    entity_type: ClassVar[str] = "process"

    process_pid: int = Field(alias="process.pid")
    process_parent_pid: int | None = Field(default=None, alias="process.parent_pid")
    process_command: str | None = Field(default=None, alias="process.command")
    process_command_line: str | None = Field(default=None, alias="process.command_line")
    process_command_args: object | None = Field(default=None, alias="process.command_args")
    process_args_count: int | None = Field(default=None, alias="process.args_count")
    process_creation_time: str = Field(alias="process.creation.time")
    process_interactive: bool | None = Field(default=None, alias="process.interactive")
    process_title: str | None = Field(default=None, alias="process.title")
    process_working_directory: str | None = Field(default=None, alias="process.working_directory")
    process_owner: str | None = Field(default=None, alias="process.owner")
    process_linux_cgroup: str | None = Field(default=None, alias="process.linux.cgroup")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.process_pid,
            self.process_creation_time,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        process_pid = int_value(attributes, "process.pid")
        if process_pid is None:
            return None
        process_creation_time = string_value(attributes, "process.creation.time")
        if process_creation_time is None:
            return None
        return cls.model_validate({
            "process.pid": process_pid,
            "process.parent_pid": int_value(attributes, "process.parent_pid"),
            "process.command": string_value(attributes, "process.command"),
            "process.command_line": string_value(attributes, "process.command_line"),
            "process.command_args": object_value(attributes, "process.command_args"),
            "process.args_count": int_value(attributes, "process.args_count"),
            "process.creation.time": process_creation_time,
            "process.interactive": bool_value(attributes, "process.interactive"),
            "process.title": string_value(attributes, "process.title"),
            "process.working_directory": string_value(attributes, "process.working_directory"),
            "process.owner": string_value(attributes, "process.owner"),
            "process.linux.cgroup": string_value(attributes, "process.linux.cgroup"),
        })


class ProcessExecutable(SemanticEntity):
    entity_type: ClassVar[str] = "process.executable"

    process_executable_build_id_htlhash: str = Field(alias="process.executable.build_id.htlhash")
    process_executable_path: str | None = Field(default=None, alias="process.executable.path")
    process_executable_build_id_go: str | None = Field(default=None, alias="process.executable.build_id.go")
    process_executable_build_id_gnu: str | None = Field(default=None, alias="process.executable.build_id.gnu")
    process_executable_name: str | None = Field(default=None, alias="process.executable.name")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.process_executable_build_id_htlhash,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        process_executable_build_id_htlhash = string_value(attributes, "process.executable.build_id.htlhash")
        if process_executable_build_id_htlhash is None:
            return None
        return cls.model_validate({
            "process.executable.build_id.htlhash": process_executable_build_id_htlhash,
            "process.executable.path": string_value(attributes, "process.executable.path"),
            "process.executable.build_id.go": string_value(attributes, "process.executable.build_id.go"),
            "process.executable.build_id.gnu": string_value(attributes, "process.executable.build_id.gnu"),
            "process.executable.name": string_value(attributes, "process.executable.name"),
        })


class ProcessRuntime(SemanticEntity):
    entity_type: ClassVar[str] = "process.runtime"

    process_runtime_name: str = Field(alias="process.runtime.name")
    process_runtime_version: str = Field(alias="process.runtime.version")
    process_runtime_description: str | None = Field(default=None, alias="process.runtime.description")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.process_runtime_name,
            self.process_runtime_version,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        process_runtime_name = string_value(attributes, "process.runtime.name")
        if process_runtime_name is None:
            return None
        process_runtime_version = string_value(attributes, "process.runtime.version")
        if process_runtime_version is None:
            return None
        return cls.model_validate({
            "process.runtime.name": process_runtime_name,
            "process.runtime.version": process_runtime_version,
            "process.runtime.description": string_value(attributes, "process.runtime.description"),
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (Process, ProcessExecutable, ProcessRuntime):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
