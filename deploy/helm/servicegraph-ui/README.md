# Servicegraph UI Chart

This chart installs the optional Flink-authoritative graph visualization. The
service applies complete graph-element `upsert` and `delete` commands and does
not perform extraction, merging, TTL, or staleness decisions.

It creates one non-root Deployment, one ClusterIP Service, and one retained RWO
PVC. It creates no CRDs or RBAC resources.
