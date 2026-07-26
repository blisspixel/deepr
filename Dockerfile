FROM python:3.12.13-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

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
