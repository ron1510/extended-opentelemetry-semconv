FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY model ./model
COPY upstream ./upstream

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "extended_otel_semconv.graph.app:app", "--host", "0.0.0.0", "--port", "8000"]
