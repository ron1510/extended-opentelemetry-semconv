# The tests intentionally exercise the module's internal rendering functions.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import extended_otel_semconv.codegen as codegen
from extended_otel_semconv.codegen import (
    GenerationPaths,
    _class_name,
    _domain_name,
    _field_name,
    _finalize,
    _generated_entity,
    _identifying_refs,
    _property_aliases,
    _python_type,
    _render_arangodb_schema,
    _render_collector_dimensions,
    _render_domain_module,
    _render_domain_parser,
    _render_package_init,
    _render_relationship_metadata,
    _safe_arangodb_name,
    _schema_hash,
    _unique_sanitized_names,
    _value_reader,
    check_files,
    generate_files,
    write_files,
)
from extended_otel_semconv.registry.model import (
    AttributeDefinition,
    EntityDefinition,
    RegistryDocument,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SOURCE = PACKAGE_ROOT / "src" / "extended_otel_semconv"


@pytest.mark.parametrize(
    ("definition", "python_type", "reader"),
    [
        (None, "object", "object_value"),
        (AttributeDefinition(id="name", type="string"), "str", "string_value"),
        (AttributeDefinition(id="count", type="int"), "int", "int_value"),
        (AttributeDefinition(id="enabled", type="boolean"), "bool", "bool_value"),
        (AttributeDefinition(id="ratio", type="double"), "object", "object_value"),
        (
            AttributeDefinition(id="method", type={"members": [{"id": "get", "value": "GET"}]}),
            "str",
            "string_value",
        ),
    ],
)
def test_attribute_types_select_runtime_readers(
    definition: AttributeDefinition | None,
    python_type: str,
    reader: str,
) -> None:
    assert _python_type(definition) == python_type
    assert _value_reader(definition) == reader


def test_generated_names_are_stable() -> None:
    assert _domain_name("cloud-platform.resource") == "cloud_platform"
    assert _class_name("cloud-platform.resource_type") == "CloudPlatformResourceType"
    assert _field_name("http.request-method/value") == "http_request_method_value"
    assert _finalize(["first", "second", "", ""]) == "first\nsecond\n"


def test_default_paths_cover_every_generated_artifact(tmp_path: Path) -> None:
    paths = codegen.default_generation_paths(tmp_path)

    assert paths.upstream_model == (
        tmp_path
        / "packages"
        / "extended-opentelemetry-semconv"
        / "upstream"
        / "otel-semconv"
        / "v1.43.0"
        / "model"
    )
    assert paths.generated_dir == (
        tmp_path
        / "packages"
        / "extended-opentelemetry-semconv"
        / "src"
        / "extended_otel_semconv"
        / "generated"
    )
    assert paths.collector_dimensions == (
        tmp_path / "deploy" / "helm" / "servicegraph-collector" / "files" / "dimensions.yaml"
    )
    assert paths.arangodb_schema == (
        tmp_path
        / "packages"
        / "extended-opentelemetry-semconv"
        / "src"
        / "extended_otel_semconv"
        / "metadata"
        / "arangodb-graph-schema.json"
    )
    assert paths.gremlin_schema == (
        tmp_path / "deploy" / "helm" / "servicegraph-gremlin" / "files" / "arangodb-graph-schema.json"
    )


def test_entity_description_separates_identifying_fields() -> None:
    entity = EntityDefinition.model_validate(
        {
            "id": "entity.app.endpoint",
            "type": "entity",
            "name": "app.endpoint",
            "attributes": [
                {"ref": "service.name", "role": "identifying"},
                {"ref": "service.version"},
            ],
        }
    )

    generated = _generated_entity(entity)

    assert generated.class_name == "AppEndpoint"
    assert generated.domain == "app"
    assert generated.field_refs == entity.attributes
    assert _identifying_refs(entity) == (entity.attributes[0],)


def test_renderers_cover_empty_single_and_multiple_domains() -> None:
    entity = EntityDefinition.model_validate(
        {
            "id": "entity.app.endpoint",
            "type": "entity",
            "name": "app.endpoint",
            "attributes": [{"ref": "service.name", "role": "identifying"}],
        }
    )
    generated = _generated_entity(entity)
    attributes = {"service.name": AttributeDefinition(id="service.name", type="string")}

    module = _render_domain_module((generated,), attributes)
    package = _render_package_init((generated,), ["app"])

    assert "class AppEndpoint(SemanticEntity):" in module
    assert 'service_name: str = Field(alias="service.name")' in module
    assert "for entity_class in (AppEndpoint,):" in module
    assert "from extended_otel_semconv.generated.app import AppEndpoint" in package
    assert _render_domain_parser(())[-1] == "    return entities"


def test_metadata_renderers_filter_relationships_and_dimensions() -> None:
    registry = RegistryDocument.model_validate(
        {
            "groups": [
                {
                    "id": "registry.app",
                    "type": "attribute_group",
                    "attributes": [
                        {"id": "service.name", "type": "string"},
                        {"id": "app.endpoint.label", "type": "string"},
                    ],
                },
                {
                    "id": "entity.service",
                    "type": "entity",
                    "name": "service",
                    "attributes": [{"ref": "service.name", "role": "identifying"}],
                },
                {
                    "id": "entity.app",
                    "type": "entity",
                    "name": "app",
                    "attributes": [
                        {"ref": "service.name", "role": "identifying"},
                        {"ref": "app.endpoint.label"},
                    ],
                },
                {
                    "id": "relationship.service_app",
                    "type": "relationship",
                    "name": "exposes",
                    "source_entity": "service",
                    "target_entity": "app",
                    "source_signals": ["service_graph"],
                },
                {
                    "id": "relationship.trace_only",
                    "type": "relationship",
                    "name": "observes",
                    "source_entity": "service",
                    "target_entity": "app",
                    "source_signals": ["trace"],
                },
            ]
        }
    )

    relationships = json.loads(_render_relationship_metadata(registry.relationships_by_id))
    dimensions = yaml.safe_load(_render_collector_dimensions(registry))

    assert [item["id"] for item in relationships] == ["relationship.service_app"]
    assert dimensions == {"dimensions": ["service.name"]}


def test_arangodb_schema_uses_registry_topology_aliases_and_identity_fields(tmp_path: Path) -> None:
    paths, _ = _generation_fixture(tmp_path)
    upstream = codegen.load_model_registry(paths.upstream_model)
    extension = codegen.load_model_registry(paths.extension_model)
    registry = codegen._merged_registry(upstream, extension)

    schema = json.loads(_render_arangodb_schema(registry, paths.upstream_lock))

    assert schema["graph_name"] == "servicegraph"
    assert schema["property_aliases"]["attributes"] == {
        "custom.rank": "custom_rank",
        "endpoint.enabled": "endpoint_enabled",
        "endpoint.retry_count": "endpoint_retry_count",
        "http.request.method": "http_request_method",
        "http.route": "http_route",
        "service.name": "service_name",
    }
    assert schema["property_aliases"]["metrics"] == {
        "service_graph.request.failed.total": "service_graph_request_failed_total",
        "service_graph.request.total": "service_graph_request_total",
    }
    assert schema["vertex_collections"] == [
        {
            "collection": "app_endpoint",
            "identifying_properties": [
                {"attribute": "service.name", "property": "service_name"},
                {"attribute": "http.request.method", "property": "http_request_method"},
                {"attribute": "http.route", "property": "http_route"},
            ],
            "semantic_type": "app.endpoint",
        },
        {
            "collection": "service",
            "identifying_properties": [{"attribute": "service.name", "property": "service_name"}],
            "semantic_type": "service",
        },
    ]
    assert schema["edge_collections"] == [
        {"collection": "exposes", "from": ["service"], "semantic_type": "exposes", "to": ["app_endpoint"]}
    ]
    schema_hash = schema["_meta"].pop("schema_hash")
    assert schema_hash == _schema_hash(schema)


def test_real_arangodb_schema_contains_every_graph_type_and_dimension_once() -> None:
    paths = codegen.default_generation_paths()
    upstream = codegen.load_model_registry(paths.upstream_model)
    extension = codegen.load_model_registry(paths.extension_model)
    registry = codegen._merged_registry(upstream, extension)
    dimensions = codegen.service_graph_dimensions(registry)
    document = json.loads(_render_arangodb_schema(registry, paths.upstream_lock))
    attributes = document["property_aliases"]["attributes"]

    assert len(dimensions) == 84
    assert tuple(attributes) == tuple(sorted(dimensions))
    assert len(attributes) == len(set(attributes))
    assert not any(name.endswith((".label", ".annotation", ".selector")) for name in attributes)
    assert len(document["vertex_collections"]) == 29
    assert len(document["edge_collections"]) == 9
    assert {item["semantic_type"] for item in document["vertex_collections"]} == codegen.service_graph_entity_names(
        registry
    )
    assert {item["semantic_type"] for item in document["edge_collections"]} == {
        relationship.name
        for relationship in registry.relationships_by_id.values()
        if "service_graph" in relationship.source_signals
    }


def test_arangodb_names_and_aliases_reject_collisions() -> None:
    assert _safe_arangodb_name("k8s.pod") == "k8s_pod"
    assert _safe_arangodb_name("service.instance") == "service_instance"
    with pytest.raises(ValueError, match="cannot be converted"):
        _safe_arangodb_name("123")
    with pytest.raises(ValueError, match="vertex collection collision"):
        _unique_sanitized_names(("app.endpoint", "app-endpoint"), "vertex collection")
    with pytest.raises(ValueError, match="reserved field"):
        _property_aliases(("element.id",))


def test_write_and_check_files_manage_stale_modules(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    generated_dir = tmp_path / "generated"
    expected = generated_dir / "expected.py"
    stale = generated_dir / "stale.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")

    write_files({expected: "expected\n"}, generated_dir)

    assert expected.read_text(encoding="utf-8") == "expected\n"
    assert not stale.exists()
    assert check_files({expected: "expected\n"}, generated_dir) == 0

    stale.write_text("stale\n", encoding="utf-8")
    expected.write_text("wrong\n", encoding="utf-8")

    assert check_files({expected: "expected\n"}, generated_dir) == 1
    output = capsys.readouterr().out
    assert "stale.py is stale" in output
    assert "expected.py is not up to date" in output


def test_main_writes_and_checks_all_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, _ = _generation_fixture(tmp_path)
    monkeypatch.setattr(codegen, "default_generation_paths", lambda: paths)

    assert codegen.main([]) == 0
    assert paths.package_lock.exists()
    assert paths.relationship_metadata.exists()
    assert paths.collector_dimensions.exists()
    assert paths.arangodb_schema.exists()
    assert paths.gremlin_schema.read_text(encoding="utf-8") == paths.arangodb_schema.read_text(encoding="utf-8")
    assert codegen.main(["--check"]) == 0

    paths.collector_dimensions.write_text("stale\n", encoding="utf-8")

    assert codegen.main(["--check"]) == 1
    assert "dimensions.yaml is not up to date" in capsys.readouterr().out

    codegen.main([])
    paths.arangodb_schema.write_text("{}\n", encoding="utf-8")

    assert codegen.main(["--check"]) == 1
    assert "arangodb-graph-schema.json is not up to date" in capsys.readouterr().out


def test_yaml_to_importable_models_and_all_generated_artifacts(tmp_path: Path) -> None:
    paths, source_root = _generation_fixture(tmp_path)

    first = generate_files(paths)
    write_files(first, paths.generated_dir)
    second = generate_files(paths)

    assert first == second
    assert check_files(second, paths.generated_dir) == 0
    assert paths.package_lock.read_text(encoding="utf-8") == '{"version": "fixture"}\n'
    assert [item["id"] for item in json.loads(paths.relationship_metadata.read_text(encoding="utf-8"))] == [
        "relationship.service_exposes_endpoint"
    ]
    assert yaml.safe_load(paths.collector_dimensions.read_text(encoding="utf-8")) == {
        "dimensions": [
            "custom.rank",
            "endpoint.enabled",
            "endpoint.retry_count",
            "http.request.method",
            "http.route",
            "service.name",
        ]
    }
    schema = json.loads(paths.arangodb_schema.read_text(encoding="utf-8"))
    assert schema["_meta"]["schema_version"] == "1"

    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(source_root)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr

    import_result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from extended_otel_semconv.generated import AppEndpoint; "
                "entity = AppEndpoint.from_attributes({"
                "'service.name': 'checkout api', "
                "'http.request.method': 'POST', "
                "'http.route': '/checkout/{id}', "
                "'endpoint.enabled': True, "
                "'endpoint.retry_count': '3'}); "
                "assert entity is not None; "
                "assert entity.endpoint_enabled is True; "
                "assert entity.endpoint_retry_count == 3; "
                "dump = entity.model_dump(by_alias=True); "
                "assert dump['endpoint.enabled'] is True; "
                "minimal = AppEndpoint.from_attributes({"
                "'service.name': 'checkout api', "
                "'http.request.method': 'POST', "
                "'http.route': '/checkout/{id}'}); "
                "assert minimal is not None; "
                "assert minimal.endpoint_enabled is None; "
                "assert entity.entity_id == "
                "'app.endpoint:checkout%20api:POST:%2Fcheckout%2F%7Bid%7D'"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(source_root)},
    )
    assert import_result.returncode == 0, import_result.stdout + import_result.stderr


def _generation_fixture(tmp_path: Path) -> tuple[GenerationPaths, Path]:
    upstream_model = tmp_path / "upstream" / "model"
    extension_model = tmp_path / "extensions"
    upstream_model.mkdir(parents=True)
    extension_model.mkdir(parents=True)
    (upstream_model / "registry.yaml").write_text(
        """
groups:
  - id: registry.fixture
    type: attribute_group
    attributes:
      - id: service.name
        type: string
      - id: http.request.method
        type:
          members:
            - id: post
              value: POST
      - id: http.route
        type: string
      - id: endpoint.enabled
        type: boolean
      - id: endpoint.retry_count
        type: int
  - id: entity.service
    type: entity
    name: service
    attributes:
      - ref: service.name
        role: identifying
""".lstrip(),
        encoding="utf-8",
    )
    (extension_model / "entities.yaml").write_text(
        """
groups:
  - id: registry.extension
    type: attribute_group
    attributes:
      - id: custom.rank
        type: int
  - id: entity.app.endpoint
    type: entity
    name: app.endpoint
    attributes:
      - ref: service.name
        role: identifying
      - ref: http.request.method
        role: identifying
      - ref: http.route
        role: identifying
      - ref: endpoint.enabled
      - ref: endpoint.retry_count
      - ref: custom.rank
  - id: relationship.trace_only
    type: relationship
    name: observes
    source_entity: service
    target_entity: app.endpoint
    source_signals: [trace]
  - id: relationship.service_exposes_endpoint
    type: relationship
    name: exposes
    source_entity: service
    target_entity: app.endpoint
    source_signals: [service_graph]
""".lstrip(),
        encoding="utf-8",
    )

    source_root = tmp_path / "source"
    package_dir = source_root / "extended_otel_semconv"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(PACKAGE_SOURCE / "entities.py", package_dir / "entities.py")
    upstream_lock = tmp_path / "upstream" / "lock.json"
    upstream_lock.write_text('{"version": "fixture"}\n', encoding="utf-8")
    return (
        GenerationPaths(
            upstream_model=upstream_model,
            extension_model=extension_model,
            upstream_lock=upstream_lock,
            generated_dir=package_dir / "generated",
            package_lock=package_dir / "metadata" / "lock.json",
            relationship_metadata=package_dir / "metadata" / "relationships.json",
            collector_dimensions=tmp_path / "collector" / "dimensions.yaml",
            arangodb_schema=package_dir / "metadata" / "arangodb-graph-schema.json",
            gremlin_schema=tmp_path / "gremlin" / "arangodb-graph-schema.json",
        ),
        source_root,
    )
