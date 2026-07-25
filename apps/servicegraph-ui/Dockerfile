# syntax=docker/dockerfile:1.7

ARG NODE_BASE_IMAGE=node:22.14.0-bookworm-slim
ARG PYTHON_BASE_IMAGE=python:3.12.13-slim-bookworm

FROM ${NODE_BASE_IMAGE} AS frontend

WORKDIR /build
ARG NPM_CONFIG_REGISTRY
ENV NPM_CONFIG_REGISTRY=${NPM_CONFIG_REGISTRY}
COPY apps/servicegraph-ui/frontend/package.json apps/servicegraph-ui/frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY apps/servicegraph-ui/frontend ./
RUN npm run build

FROM ${PYTHON_BASE_IMAGE} AS runtime

ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
ENV HOME=/tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build
COPY packages/extended-opentelemetry-semconv ./packages/extended-opentelemetry-semconv
COPY apps/servicegraph-ui ./apps/servicegraph-ui
RUN --mount=type=cache,target=/tmp/pip-cache \
    PIP_CACHE_DIR=/tmp/pip-cache python -m pip install \
      ./apps/servicegraph-ui \
      ./packages/extended-opentelemetry-semconv

RUN groupadd --gid 10001 servicegraph \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin servicegraph \
    && mkdir -p /app/static /data \
    && chown -R 10001:10001 /app /data
COPY --from=frontend --chown=10001:10001 /build/dist/ /app/static/

WORKDIR /app
USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["servicegraph-ui"]
