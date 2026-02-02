FROM python:3.11-slim

# Security: non-root user
RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

# Install dependencies first (cache layer)
COPY pyproject.toml setup.py README.md ./
COPY deepr/__init__.py deepr/__init__.py
RUN pip install --no-cache-dir .

# Copy application code
COPY deepr/ deepr/
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
