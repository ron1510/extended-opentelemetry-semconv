FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY model ./model
COPY upstream ./upstream

RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "extended_otel_semconv.services.graph_loader.cli"]
