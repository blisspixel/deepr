# Test quick reference

```bash
# Exact no-key CI scope
pytest tests/unit/ --ignore=tests/data -q

# Coverage gate
pytest tests/unit/ --ignore=tests/data -q --cov=deepr --cov-report=term-missing

# Lint and format source
ruff check src/deepr/
ruff format --check src/deepr/

# Strict type islands
mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/core src/deepr/providers src/deepr/mcp src/deepr/security src/deepr/queue src/deepr/storage src/deepr/tools src/deepr/routing src/deepr/worker src/deepr/webhooks src/deepr/a2a src/deepr/skills
```

Do not run bare `pytest` and do not set provider keys for the unit suite. Live
integration tests are explicit, potentially paid, and outside CI. The old
keyboard expert scripts and metered agentic-chat examples no longer exist and
must not be used as release validation.
