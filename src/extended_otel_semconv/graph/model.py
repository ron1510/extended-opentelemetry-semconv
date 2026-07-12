from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

SourceSignal: TypeAlias = Literal["trace", "service_graph"]


class GraphNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: str
    first_seen: float
    last_seen: float
    observations: int = 1
    sources: dict[str, int] = Field(default_factory=dict)
    attributes: dict[str, object] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    type: str
    first_seen: float
    last_seen: float
    observations: int = 1
    sources: dict[str, int] = Field(default_factory=dict)
    attributes: dict[str, object] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}->{self.type}->{self.target}"


class GraphSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    entities: list[GraphNode]
    edges: list[GraphEdge]
