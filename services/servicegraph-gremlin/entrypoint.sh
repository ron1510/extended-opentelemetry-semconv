#!/usr/bin/env bash
set -euo pipefail

readonly template_dir=/etc/servicegraph-gremlin
readonly runtime_dir=/opt/gremlin-server/runtime-conf

envsubst < "${template_dir}/arangodb.yaml" > "${runtime_dir}/arangodb.yaml"
envsubst < "${template_dir}/gremlin-server.yaml" > "${runtime_dir}/gremlin-server.yaml"
cp "${template_dir}/init.groovy" "${runtime_dir}/init.groovy"

exec /opt/gremlin-server/bin/gremlin-server.sh "${runtime_dir}/gremlin-server.yaml"
