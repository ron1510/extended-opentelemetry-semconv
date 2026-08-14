from __future__ import annotations

from servicegraph_indexer.schema import load_graph_schema


def test_generated_schema_is_valid_and_complete() -> None:
    schema = load_graph_schema()

    assert schema.graph_name == "servicegraph"
    assert len(schema.vertex_collections) == 29
    assert len(schema.edge_collections) == 9
    assert schema.vertices_by_type["service.instance"].collection == "service_instance"
    assert schema.vertices_by_type["k8s.pod"].collection == "k8s_pod"
    assert schema.edges_by_type["calls"].collection == "calls"
    assert schema.property_aliases.attributes["service.name"] == "service_name"
    assert schema.property_aliases.metrics["service_graph.request.total"] == "service_graph_request_total"
