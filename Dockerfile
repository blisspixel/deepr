FROM python:3.15.1-slim@sha256:08275f764e022331c6d3e3ca55d8cce01fa4684b02111adf0445d71806fe7941

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install the exact lock-selected package set.
RUN python -c "import pip; assert tuple(map(int, pip.__version__.split('.'))) >= (26, 2, 2)"
RUN python -m pip install --no-cache-dir uv==0.13.5
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
