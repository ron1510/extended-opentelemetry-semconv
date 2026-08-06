# syntax=docker/dockerfile:1.7

ARG PYTHON_BASE_IMAGE=python:3.12.13-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}

ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
ENV HOME=/tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build
COPY packages/extended-opentelemetry-semconv ./packages/extended-opentelemetry-semconv
COPY services/servicegraph-access ./services/servicegraph-access
RUN --mount=type=cache,target=/tmp/pip-cache \
    PIP_CACHE_DIR=/tmp/pip-cache python -m pip install \
      ./services/servicegraph-access \
      ./packages/extended-opentelemetry-semconv

RUN groupadd --gid 10001 servicegraph \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin servicegraph

WORKDIR /app
USER 10001:10001
ENTRYPOINT ["servicegraph-access-init"]
