FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install the exact lock-selected application and AWS worker dependencies.
RUN pip install --no-cache-dir uv==0.13.0
COPY pyproject.toml uv.lock setup.py README.md LICENSE MANIFEST.in ./
COPY src/ src/
COPY skills/ skills/
RUN uv sync --frozen --no-dev --no-editable --extra aws

ENV PATH="/app/.venv/bin:$PATH"

# Copy worker entry point.
COPY deploy/aws/src/worker/worker.py ./worker.py

# Switch to non-root user
USER deepr

# Worker entry point
CMD ["python", "worker.py"]
