from __future__ import annotations

import json
from pathlib import Path

from extended_otel_semconv.upstream.drift import compare_model_dirs


def test_detects_attribute_and_entity_drift_from_local_snapshots(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_model = old_root / "k8s"
    new_model = new_root / "k8s"
    old_model.mkdir(parents=True)
    new_model.mkdir(parents=True)

    _write_model(old_model, pod_brief="Old pod", include_namespace=False)
    _write_model(new_model, pod_brief="New pod", include_namespace=True)

    report = compare_model_dirs(old_root, new_root)

    assert report.added_attributes == ("k8s.namespace.name",)
    assert report.changed_entities == ("k8s.pod",)


def _write_model(path: Path, pod_brief: str, include_namespace: bool) -> None:
    attributes = [{"id": "k8s.pod.uid", "type": "string", "stability": "stable", "brief": "Pod UID"}]
    entity_refs = [{"ref": "k8s.pod.uid"}]
    if include_namespace:
        attributes.append({"id": "k8s.namespace.name", "type": "string", "stability": "stable", "brief": "Namespace"})
        entity_refs.append({"ref": "k8s.namespace.name"})
    (path / "registry.yaml").write_text(
        json.dumps({"groups": [{"id": "registry.k8s", "type": "attribute_group", "attributes": attributes}]}),
        encoding="utf-8",
    )
    (path / "entities.yaml").write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "id": "entity.k8s.pod",
                        "type": "entity",
                        "name": "k8s.pod",
                        "stability": "development",
                        "brief": pod_brief,
                        "attributes": entity_refs,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
