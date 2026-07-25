# syntax=docker/dockerfile:1.7

ARG MAVEN_BASE_IMAGE=maven:3.9.11-eclipse-temurin-11
ARG PYTHON_BASE_IMAGE=python:3.12.13-slim-bookworm
ARG FLINK_BASE_IMAGE=flink:2.2.1-scala_2.12-java11

FROM ${MAVEN_BASE_IMAGE} AS java-runtime

WORKDIR /build
COPY apps/otel-servicegraph-diff/runtime/java/pom.xml ./pom.xml
COPY apps/otel-servicegraph-diff/runtime/java/src ./src
RUN --mount=type=secret,id=maven_settings,required=false \
    if [ -f /run/secrets/maven_settings ]; then \
      mvn --batch-mode --no-transfer-progress --settings /run/secrets/maven_settings package; \
    else \
      mvn --batch-mode --no-transfer-progress package; \
    fi

FROM ${PYTHON_BASE_IMAGE} AS python-build

WORKDIR /dependencies
ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

COPY packages/extended-opentelemetry-semconv ./packages/extended-opentelemetry-semconv
COPY apps/otel-servicegraph-diff ./apps/otel-servicegraph-diff
RUN --mount=type=cache,target=/tmp/pip-cache \
    PIP_CACHE_DIR=/tmp/pip-cache python -m pip install \
      ./apps/otel-servicegraph-diff \
      ./packages/extended-opentelemetry-semconv

FROM ${PYTHON_BASE_IMAGE} AS runtime-layout

RUN mkdir -p \
      /layout/opt/flink/log \
      /layout/opt/application \
      /layout/flink-state \
    && chgrp -R 0 /layout \
    && chmod -R g=u /layout

FROM ${FLINK_BASE_IMAGE} AS runtime-base

COPY --from=python-build --chown=flink:0 /usr/local /usr/local
COPY --from=runtime-layout --chown=flink:0 /layout/ /
COPY --chown=flink:0 packages/extended-opentelemetry-semconv/src/extended_otel_semconv /opt/application/extended_otel_semconv
COPY --chown=flink:0 apps/otel-servicegraph-diff/src/otel_servicegraph_diff /opt/application/otel_servicegraph_diff
COPY --from=java-runtime --chown=flink:0 --chmod=0440 \
  /build/target/interaction-serializer.jar \
  /opt/flink/lib/interaction-serializer.jar
COPY --from=java-runtime --chown=flink:0 --chmod=0440 \
  /build/target/runtime/flink-sql-connector-kafka-5.0.0-2.2.jar \
  /opt/flink/lib/flink-sql-connector-kafka-5.0.0-2.2.jar

ENV PYFLINK_CLIENT_EXECUTABLE=/usr/local/bin/python3.12
ENV PYTHONPATH=/opt/application
ENV HOME=/tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER flink

FROM runtime-base AS runtime
