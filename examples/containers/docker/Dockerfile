# Multi-stage build for minimal image size
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir build hatchling

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/

# Build wheel
RUN python -m build --wheel

# --- Runtime stage ---
FROM python:3.11-slim

WORKDIR /app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy wheel from builder
COPY --from=builder /app/dist/*.whl ./

# Install the package
RUN pip install --no-cache-dir *.whl && rm *.whl

# Switch to non-root user
USER appuser

# Set Python to run unbuffered for better logging
ENV PYTHONUNBUFFERED=1

# Default command
ENTRYPOINT ["python", "-m", "connector.main"]

# Default arguments (can be overridden)
CMD ["--mode", "FULL"]
