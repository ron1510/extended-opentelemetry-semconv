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

FROM ${PYTHON_BASE_IMAGE} AS python-runtime

FROM python-runtime AS python-dependencies

WORKDIR /dependencies
ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
COPY packages/extended-opentelemetry-semconv/pyproject.toml ./semantic-pyproject.toml
COPY apps/otel-servicegraph-diff/pyproject.toml ./application-pyproject.toml
COPY scripts/runtime_dependencies.py ./runtime_dependencies.py
RUN --mount=type=cache,target=/tmp/pip-cache \
    PIP_CACHE_DIR=/tmp/pip-cache python runtime_dependencies.py \
      --exclude-project extended-opentelemetry-semconv \
      semantic-pyproject.toml \
      application-pyproject.toml \
      > runtime-requirements.txt \
    && PIP_CACHE_DIR=/tmp/pip-cache python -m pip install \
      --requirement runtime-requirements.txt

FROM python-runtime AS runtime-layout

RUN mkdir -p \
      /layout/opt/flink/checkpoints \
      /layout/opt/flink/log \
      /layout/opt/flink/savepoints \
      /layout/flink-state \
      /layout/workspace \
    && chgrp -R 0 /layout \
    && chmod -R g=u /layout

FROM python-dependencies AS python-development

WORKDIR /workspace
COPY pyproject.toml ./pyproject.toml
COPY packages ./packages
COPY apps/otel-servicegraph-diff ./apps/otel-servicegraph-diff
COPY tools ./tools
COPY tests ./tests
COPY scripts ./scripts
COPY model ./model
COPY upstream ./upstream
COPY deploy ./deploy
RUN --mount=type=cache,target=/tmp/pip-cache \
    PIP_CACHE_DIR=/tmp/pip-cache python -m pip install --no-deps \
      --editable packages/extended-opentelemetry-semconv \
      --editable apps/otel-servicegraph-diff \
    && PIP_CACHE_DIR=/tmp/pip-cache python -m pip install \
      confluent-kafka==2.15.0 \
      hypothesis==6.158.0 \
      "pyright[nodejs]==1.1.411" \
      pytest==9.1.1 \
      ruff==0.15.22

FROM ${FLINK_BASE_IMAGE} AS runtime-base

COPY --from=python-dependencies --chown=flink:0 /usr/local /usr/local
COPY --from=runtime-layout --chown=flink:0 /layout/ /
COPY --from=java-runtime --chown=flink:0 --chmod=0440 \
  /build/target/interaction-serializer.jar \
  /opt/flink/lib/interaction-serializer.jar
COPY --from=java-runtime --chown=flink:0 --chmod=0440 \
  /build/target/runtime/flink-sql-connector-kafka-5.0.0-2.2.jar \
  /opt/flink/lib/flink-sql-connector-kafka-5.0.0-2.2.jar

ENV PYFLINK_CLIENT_EXECUTABLE=/usr/local/bin/python3.12
ENV HOME=/tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER flink

FROM runtime-base AS development

WORKDIR /workspace
COPY --from=python-development --chown=flink:0 /usr/local /usr/local
COPY --from=python-development --chown=flink:0 /workspace /workspace

ENV PYTHONPATH=/workspace/tools
USER flink

FROM runtime-base AS runtime
