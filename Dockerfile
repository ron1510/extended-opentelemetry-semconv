ARG PYTHON_BASE_IMAGE=python:3.12.13-slim-bookworm
ARG FLINK_BASE_IMAGE=flink:2.2.1-scala_2.12-java17

FROM ${PYTHON_BASE_IMAGE} AS python-runtime

FROM ${FLINK_BASE_IMAGE}

USER root
COPY --from=python-runtime /usr/local /usr/local

WORKDIR /app

COPY pyproject.toml requirements.lock README.md ./
COPY vendor/flink/*.jar /opt/flink/lib/
COPY vendor/debian/libatomic1_12.2.0-14+deb12u1_amd64.deb /tmp/libatomic1.deb

ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
RUN ln -sf /usr/local/bin/python3.12 /usr/local/bin/python \
    && mkdir -p src/extended_otel_semconv \
    && touch src/extended_otel_semconv/__init__.py \
    && python -m pip install --no-cache-dir --constraint requirements.lock . \
    && python -m pip install --no-cache-dir --constraint requirements.lock hypothesis "pyright[nodejs]" pytest ruff \
    && rm -rf src \
    && mkdir -p /opt/flink/checkpoints /opt/flink/savepoints /flink-state \
    && chgrp -R 0 /app /opt/flink /flink-state \
    && chmod -R g=u /app /opt/flink /flink-state

RUN dpkg-deb --extract /tmp/libatomic1.deb /tmp/libatomic1 \
    && cp /tmp/libatomic1/usr/lib/x86_64-linux-gnu/libatomic.so.1.2.0 /usr/local/lib/ \
    && ln -s /usr/local/lib/libatomic.so.1.2.0 /usr/local/lib/libatomic.so.1 \
    && ldconfig \
    && rm -rf /tmp/libatomic1 /tmp/libatomic1.deb

COPY src ./src
COPY model ./model
COPY upstream ./upstream
COPY scripts ./scripts
COPY tests ./tests

RUN python -m pip install --no-cache-dir --no-deps -e . \
    && chgrp -R 0 /app \
    && chmod -R g=u /app

ENV PYFLINK_CLIENT_EXECUTABLE=/usr/local/bin/python
ENV HOME=/tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER 1001

CMD ["flink", "run", "-d", "-m", "flink-jobmanager:8081", "-py", "/app/src/extended_otel_semconv/services/interaction_diff/cli.py"]
