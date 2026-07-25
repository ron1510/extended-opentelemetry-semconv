"""FastAPI application for the interaction graph projection."""

# FastAPI registers these local endpoint functions through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from servicegraph_ui.config import VisualizationConfig
from servicegraph_ui.consumer import ProjectionConsumer
from servicegraph_ui.models import EntityView, EventView, GraphView, InteractionView, StatusView
from servicegraph_ui.repository import ProjectionRepository


def create_app(
    config: VisualizationConfig | None = None,
    repository: ProjectionRepository | None = None,
    *,
    start_consumer: bool = True,
) -> FastAPI:
    settings = config or VisualizationConfig()
    projection = repository or ProjectionRepository(settings.database_path, settings.recent_event_limit)
    projection.initialize()
    consumer = ProjectionConsumer(settings, projection)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        if start_consumer:
            consumer.start()
        yield
        if start_consumer:
            consumer.stop()

    app = FastAPI(title="Servicegraph Visualization API", version="1.0.0", lifespan=lifespan)
    app.state.config = settings
    app.state.repository = projection
    app.state.consumer = consumer

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        if start_consumer and not consumer.status.running:
            raise HTTPException(status_code=503, detail=consumer.status.error or "Kafka consumer is not running")
        return {"status": "ready"}

    @app.get("/api/v1/status", response_model=StatusView)
    def status() -> StatusView:
        interactions, entities, edges = projection.counts()
        return StatusView(
            consumer_running=consumer.status.running,
            consumer_error=consumer.status.error,
            topic=settings.topic,
            interactions=interactions,
            entities=entities,
            edges=edges,
            last_event_at_unix_ms=consumer.status.last_event_at_unix_ms,
        )

    @app.get("/api/v1/graph", response_model=GraphView)
    def graph(
        q: str | None = Query(default=None, max_length=200),
        entity_type: str | None = Query(default=None, max_length=100),
        edge_type: str | None = Query(default=None, max_length=100),
    ) -> GraphView:
        return projection.graph(q, entity_type, edge_type)

    @app.get("/api/v1/entities", response_model=tuple[EntityView, ...])
    def entities(
        q: str | None = Query(default=None, max_length=200),
        entity_type: str | None = Query(default=None, max_length=100),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> tuple[EntityView, ...]:
        return projection.entities(q, entity_type, limit, offset)

    @app.get("/api/v1/interactions", response_model=tuple[InteractionView, ...])
    def interactions(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> tuple[InteractionView, ...]:
        return projection.interactions(limit, offset)

    @app.get("/api/v1/interactions/{interaction_id}", response_model=InteractionView)
    def interaction(interaction_id: str) -> InteractionView:
        result = projection.interaction(interaction_id)
        if result is None:
            raise HTTPException(status_code=404, detail="interaction not found")
        return result

    @app.get("/api/v1/events", response_model=tuple[EventView, ...])
    def events(limit: int = Query(default=100, ge=1, le=1_000)) -> tuple[EventView, ...]:
        return projection.events(limit)

    if settings.static_dir.exists():
        assets = settings.static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            del path
            return FileResponse(settings.static_dir / "index.html")

    return app
