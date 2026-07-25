# Servicegraph UI Chart

This chart installs the optional Flink-authoritative interaction graph
visualization. The service applies only Flink `upsert` and `delete` commands; it
does not evaluate interaction TTL or staleness.

It creates one non-root Deployment, one ClusterIP Service, and one retained RWO
PVC. It creates no CRDs or RBAC resources.
