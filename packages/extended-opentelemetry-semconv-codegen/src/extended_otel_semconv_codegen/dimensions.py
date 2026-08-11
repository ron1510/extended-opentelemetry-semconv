"""Registry-driven service graph dimension selection."""

from __future__ import annotations

from extended_otel_semconv_codegen.registry.model import AttributeDefinition, EntityDefinition, RegistryDocument

TEMPLATE_SUFFIXES = (".label", ".annotation", ".selector")


def service_graph_dimensions(registry: RegistryDocument) -> tuple[str, ...]:
    """Return servicegraph dimensions from modeled servicegraph entity fields."""

    entity_names = service_graph_entity_names(registry)
    dimensions: set[str] = set()
    for entity_name in entity_names:
        entity = registry.entities_by_name.get(entity_name)
        if entity is None:
            continue
        dimensions.update(
            attribute_ref.ref
            for attribute_ref in entity.attributes
            if include_dimension_ref(attribute_ref.ref, registry.attributes_by_id.get(attribute_ref.ref))
        )
    return tuple(sorted(dimensions))


def service_graph_entity_names(registry: RegistryDocument) -> set[str]:
    entity_names: set[str] = set()
    for relationship in registry.relationships_by_id.values():
        if "service_graph" not in relationship.source_signals:
            continue
        entity_names.add(relationship.source_entity)
        entity_names.add(relationship.target_entity)
    return entity_names


def include_dimension_ref(attribute_ref: str, attribute: AttributeDefinition | None = None) -> bool:
    if any(attribute_ref.endswith(suffix) for suffix in TEMPLATE_SUFFIXES):
        return False
    if attribute is None:
        return True
    return is_scalar_attribute(attribute)


def entity_dimensions(entity: EntityDefinition) -> tuple[str, ...]:
    return tuple(sorted(ref.ref for ref in entity.attributes if include_dimension_ref(ref.ref)))


def is_scalar_attribute(attribute: AttributeDefinition) -> bool:
    attribute_type = attribute.type
    if isinstance(attribute_type, dict):
        return "members" in attribute_type
    if not isinstance(attribute_type, str):
        return False
    return attribute_type in {"boolean", "double", "int", "string"}
