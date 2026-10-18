FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce AS build

# Compile source-only full-extra dependencies without shipping build tools.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.0
COPY pyproject.toml uv.lock setup.py README.md LICENSE MANIFEST.in ./
COPY src/ src/
COPY skills/ skills/
RUN uv sync --frozen --no-dev --no-editable --extra full

FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEEPR_DATA_DIR=/data \
    DEEPR_MCP_KEYS_PATH=/data/security/mcp_keys.json \
    DEEPR_MCP_HTTP_MAX_CONCURRENCY=32

RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

COPY --from=build /app /app

ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p /data/security /data/reports && chown -R deepr:deepr /data

USER deepr

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/mcp/health', timeout=3).read()" || exit 1

ENTRYPOINT ["deepr"]
CMD ["mcp", "serve", "--http", "--host", "0.0.0.0", "--port", "8765", "--path", "/mcp", "--keys-path", "/data/security/mcp_keys.json"]
