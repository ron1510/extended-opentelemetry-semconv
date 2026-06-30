from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_interfaces() -> set[str]:
    path = ROOT / "registry" / "interfaces.yaml"
    registry = load_json(path)
    require(registry["kind"] == "asset_interface_registry", f"{path}: wrong kind")
    interfaces = registry.get("interfaces")
    require(isinstance(interfaces, list) and interfaces, f"{path}: missing interfaces")

    names: set[str] = set()
    for item in interfaces:
        name = item.get("name")
        require(isinstance(name, str) and name, f"{path}: interface missing name")
        require(name not in names, f"{path}: duplicate interface {name}")
        names.add(name)
        require(isinstance(item.get("identity_evidence"), list), f"{name}: missing identity_evidence")
        require(isinstance(item.get("applicable_scopes"), list), f"{name}: missing applicable_scopes")

    for item in interfaces:
        for parent in item.get("extends", []):
            require(parent in names, f"{item['name']}: unknown parent interface {parent}")

    return names


def validate_relationships(interface_names: set[str]) -> set[str]:
    path = ROOT / "registry" / "relationships.yaml"
    registry = load_json(path)
    require(registry["kind"] == "asset_relationship_registry", f"{path}: wrong kind")
    relationships = registry.get("relationships")
    require(isinstance(relationships, list) and relationships, f"{path}: missing relationships")

    relationship_types: set[str] = set()
    known_external = {"k8s.cluster", "k8s.namespace", "datacenter", "telemetry.source", "alert.contract"}
    known_types = interface_names | known_external | {"*"}

    for item in relationships:
        rel_type = item.get("type")
        require(isinstance(rel_type, str) and rel_type, f"{path}: relationship missing type")
        require(rel_type not in relationship_types, f"{path}: duplicate relationship {rel_type}")
        relationship_types.add(rel_type)

        for pair in item.get("allowed_pairs", []):
            require(isinstance(pair, list) and len(pair) == 2, f"{rel_type}: invalid allowed pair {pair}")
            require(pair[0] in known_types, f"{rel_type}: unknown source type {pair[0]}")
            require(pair[1] in known_types, f"{rel_type}: unknown target type {pair[1]}")

    return relationship_types


def validate_evidence_sources(interface_names: set[str], relationship_types: set[str]) -> None:
    path = ROOT / "registry" / "evidence-sources.yaml"
    registry = load_json(path)
    require(registry["kind"] == "asset_evidence_source_registry", f"{path}: wrong kind")
    sources = registry.get("sources")
    require(isinstance(sources, list) and sources, f"{path}: missing sources")

    for source in sources:
        name = source.get("name")
        require(isinstance(name, str) and name, f"{path}: source missing name")
        for key in ("primary_for", "secondary_for"):
            for interface_name in source.get(key, []):
                require(interface_name in interface_names, f"{name}: unknown interface {interface_name}")
        for rel_type in source.get("relationship_evidence", []):
            require(rel_type in relationship_types, f"{name}: unknown relationship {rel_type}")


def validate_example_shape(path: Path, relationship_types: set[str]) -> None:
    data = load_json(path)
    evidence = data.get("evidence")
    require(isinstance(evidence, list) and evidence, f"{path}: missing evidence")

    evidence_ids = set()
    for item in evidence:
        for key in ("evidence_id", "source", "observed_at", "attributes"):
            require(key in item, f"{path}: evidence item missing {key}")
        require(isinstance(item["attributes"], dict), f"{path}: evidence attributes must be an object")
        evidence_ids.add(item["evidence_id"])

    for entity in data.get("expected_entities", []):
        for key in ("entity_id", "interfaces", "identity", "confidence", "evidence_ids", "first_seen", "last_seen"):
            require(key in entity, f"{path}: expected entity missing {key}")
        require(0 <= entity["confidence"] <= 1, f"{path}: entity confidence out of range")
        require(set(entity["evidence_ids"]).issubset(evidence_ids), f"{path}: entity references unknown evidence")

    for relationship in data.get("expected_relationships", []):
        for key in (
            "relationship_id",
            "type",
            "source_entity_id",
            "target_entity_id",
            "confidence",
            "evidence_ids",
            "first_seen",
            "last_seen",
        ):
            require(key in relationship, f"{path}: expected relationship missing {key}")
        require(relationship["type"] in relationship_types, f"{path}: unknown relationship type {relationship['type']}")
        require(0 <= relationship["confidence"] <= 1, f"{path}: relationship confidence out of range")
        require(set(relationship["evidence_ids"]).issubset(evidence_ids), f"{path}: relationship references unknown evidence")


def validate_contract_example(path: Path, interface_names: set[str]) -> None:
    contract = load_json(path)
    for key in ("contract_id", "target_interface", "required_evidence_fields", "allowed_dimensions", "rollup_path"):
        require(key in contract, f"{path}: contract missing {key}")
    require(contract["target_interface"] in interface_names, f"{path}: unknown target interface")
    for key in ("required_evidence_fields", "allowed_dimensions", "rollup_path"):
        require(isinstance(contract[key], list), f"{path}: {key} must be a list")


def validate_schema_files() -> None:
    for path in sorted((ROOT / "schemas").glob("*.json")):
        schema = load_json(path)
        require(schema.get("$schema"), f"{path}: missing $schema")
        require(schema.get("title"), f"{path}: missing title")
        require(schema.get("type") == "object", f"{path}: schema root must be object")


def main() -> None:
    interface_names = validate_interfaces()
    relationship_types = validate_relationships(interface_names)
    validate_evidence_sources(interface_names, relationship_types)
    validate_schema_files()

    for path in sorted((ROOT / "examples").glob("*evidence.json")):
        validate_example_shape(path, relationship_types)
    validate_contract_example(ROOT / "examples" / "metric-alert-contract.json", interface_names)

    print("registry validation passed")


if __name__ == "__main__":
    main()
