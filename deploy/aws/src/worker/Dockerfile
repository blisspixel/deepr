FROM python:3.15.2-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install the exact lock-selected application and AWS worker dependencies.
RUN python -c "import pip; assert tuple(map(int, pip.__version__.split('.'))) >= (26, 2, 2)"
RUN python -m pip install --no-cache-dir uv==0.13.8
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
