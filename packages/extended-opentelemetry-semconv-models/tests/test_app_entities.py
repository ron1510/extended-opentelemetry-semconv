from __future__ import annotations

from extended_otel_semconv import AppEndpoint, K8sPod, Service, ServiceNamespace, entities_from_attributes


def app_entities_from_attributes(attributes: dict[str, object]) -> list[AppEndpoint]:
    return [entity for entity in entities_from_attributes(attributes) if isinstance(entity, AppEndpoint)]


def test_service_attributes_create_generated_upstream_entities() -> None:
    entities = entities_from_attributes(
        {
            "service.name": "checkout-api",
            "service.namespace": "payments",
            "service.version": "1.8.3",
            "service.instance.id": "checkout-api-7bc8c9c9cc-j62md/app",
        }
    )

    assert [entity.entity_type for entity in entities if entity.entity_type.startswith("service")] == [
        "service",
        "service.instance",
        "service.namespace",
    ]
    assert any(isinstance(entity, Service) for entity in entities)
    assert any(isinstance(entity, ServiceNamespace) for entity in entities)


def test_http_route_without_namespace_does_not_create_app_endpoint() -> None:
    entities = app_entities_from_attributes(
        {
            "service.name": "checkout-api",
            "http.request.method": "POST",
            "http.route": "/checkout/{cart_id}",
        }
    )

    assert entities == []


def test_http_route_attributes_create_app_endpoint_entity() -> None:
    entities = app_entities_from_attributes(
        {
            "service.name": "checkout-api",
            "service.namespace": "payments",
            "http.request.method": "POST",
            "http.route": "/checkout/{cart_id}",
        }
    )

    assert [entity.entity_type for entity in entities] == ["app.endpoint"]
    assert isinstance(entities[0], AppEndpoint)
    assert entities[0].entity_id == "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D"


def test_missing_service_name_creates_no_app_entities() -> None:
    entities = app_entities_from_attributes(
        {
            "http.request.method": "POST",
            "http.route": "/checkout/{cart_id}",
        }
    )

    assert entities == []


def test_incomplete_endpoint_attributes_create_no_custom_entities() -> None:
    entities = app_entities_from_attributes(
        {
            "service.name": "checkout-api",
            "http.request.method": "POST",
        }
    )

    assert entities == []


def test_service_and_endpoint_ids_work_without_namespace() -> None:
    entities = app_entities_from_attributes(
        {
            "service.name": "checkout-api",
            "http.request.method": "GET",
            "http.route": "/health",
        }
    )

    assert entities == []


def test_top_level_parser_creates_upstream_and_extension_entities() -> None:
    entities = entities_from_attributes(
        {
            "k8s.cluster.uid": "cluster-123",
            "k8s.namespace.name": "checkout",
            "k8s.pod.uid": "4e2b0bb9-4700-4f20-bb6f-c6e2b5975c6b",
            "service.name": "checkout-api",
            "service.namespace": "payments",
            "http.request.method": "POST",
            "http.route": "/checkout/{cart_id}",
        }
    )

    entity_types = [entity.entity_type for entity in entities]
    assert "service" in entity_types
    assert "service.namespace" in entity_types
    assert "k8s.pod" in entity_types
    assert "app.endpoint" in entity_types
    assert any(isinstance(entity, Service) for entity in entities)
    assert any(isinstance(entity, K8sPod) for entity in entities)
    assert any(isinstance(entity, AppEndpoint) for entity in entities)
