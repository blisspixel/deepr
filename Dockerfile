FROM python:3.12-slim

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install the package (src layout: pyproject + README + src/ are all needed)
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

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
