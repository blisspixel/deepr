FROM python:3.12.13-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEEPR_DATA_DIR=/data \
    DEEPR_MCP_KEYS_PATH=/data/security/mcp_keys.json \
    DEEPR_MCP_HTTP_MAX_CONCURRENCY=32

RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.32

COPY pyproject.toml uv.lock setup.py README.md LICENSE MANIFEST.in ./
COPY src/ src/
COPY skills/ skills/

RUN uv sync --frozen --no-dev --no-editable --extra full

ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p /data/security /data/reports && chown -R deepr:deepr /data

USER deepr

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/mcp/health', timeout=3).read()" || exit 1

ENTRYPOINT ["deepr"]
CMD ["mcp", "serve", "--http", "--host", "0.0.0.0", "--port", "8765", "--path", "/mcp", "--keys-path", "/data/security/mcp_keys.json"]
