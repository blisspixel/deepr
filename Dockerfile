FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install the exact lock-selected package set.
RUN pip install --no-cache-dir uv==0.11.32
COPY pyproject.toml uv.lock setup.py README.md LICENSE MANIFEST.in ./
COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH"

# Supporting assets
COPY skills/ skills/

# Create data directory owned by deepr user
RUN mkdir -p /app/data/reports && chown -R deepr:deepr /app/data

# Switch to non-root user
USER deepr

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import deepr; print('ok')" || exit 1

# MCP server entry point (stdio transport)
ENTRYPOINT ["python", "-m", "deepr.mcp.server"]
