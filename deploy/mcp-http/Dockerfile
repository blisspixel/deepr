FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEEPR_DATA_DIR=/data \
    DEEPR_MCP_KEYS_PATH=/data/security/mcp_keys.json \
    DEEPR_MCP_HTTP_MAX_CONCURRENCY=32

RUN groupadd -r deepr && useradd -r -g deepr -u 1000 deepr

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
COPY skills/ skills/

RUN pip install --no-cache-dir ".[full]"

RUN mkdir -p /data/security /data/reports && chown -R deepr:deepr /data

USER deepr

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/mcp/health', timeout=3).read()" || exit 1

ENTRYPOINT ["deepr"]
CMD ["mcp", "serve", "--http", "--host", "0.0.0.0", "--port", "8765", "--path", "/mcp", "--keys-path", "/data/security/mcp_keys.json"]
