FROM python:3.12.13-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install the exact lock-selected application and AWS worker dependencies.
RUN pip install --no-cache-dir uv==0.11.32
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
