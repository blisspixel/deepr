FROM python:3.15.1-slim@sha256:08275f764e022331c6d3e3ca55d8cce01fa4684b02111adf0445d71806fe7941

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install the exact lock-selected application and AWS worker dependencies.
RUN python -c "import pip; assert tuple(map(int, pip.__version__.split('.'))) >= (26, 2, 2)"
RUN python -m pip install --no-cache-dir uv==0.13.5
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
