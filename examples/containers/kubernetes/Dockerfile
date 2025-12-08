# Use the same Dockerfile from the docker example
# This is included for completeness - in practice, you might
# reference the docker example's Dockerfile

FROM python:3.11-slim as builder

WORKDIR /app

RUN pip install --no-cache-dir build hatchling

COPY pyproject.toml .
COPY src/ ./src/

RUN python -m build --wheel

FROM python:3.11-slim

WORKDIR /app

RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /app/dist/*.whl ./

RUN pip install --no-cache-dir *.whl && rm *.whl

USER appuser

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "connector.main"]
CMD ["--mode", "FULL"]
