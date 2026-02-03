# Contributing to Deepr

Thanks for your interest in contributing. This document covers the basics.

## Setup

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr
pip install -e ".[dev]"
pre-commit install
```

## Development Workflow

1. Create a branch from `main`.
2. Make your changes.
3. Run linting and tests before committing:

```bash
ruff check deepr/
python -m pytest tests/unit/ --ignore=tests/data -q --tb=short
```

4. Pre-commit hooks run automatically on `git commit` (ruff lint, ruff format, trailing whitespace, debug statement detection).
5. Open a pull request against `main`.

## Code Style

- **Formatter**: ruff-format (line length 120)
- **Linter**: ruff (E, F, W, I rules)
- **Target**: Python 3.9+

The pre-commit hooks enforce these automatically. No need to run formatters manually.

## Testing

```bash
# Run unit tests
python -m pytest tests/unit/ --ignore=tests/data -q

# Run with coverage
python -m pytest tests/unit/ --ignore=tests/data --cov=deepr --cov-report=term-missing

# Run a specific test file
python -m pytest tests/unit/test_config.py -v
```

Coverage minimum is 60% on core modules. CI enforces this on every push and PR.

## Project Structure

- `deepr/` -- Main package
- `deepr/cli/` -- CLI commands (Click)
- `deepr/cli/commands/semantic/` -- Semantic commands (research, artifacts, experts)
- `deepr/core/` -- Research orchestration, costs, context
- `deepr/providers/` -- Model provider integrations (OpenAI, Gemini, Grok, Azure)
- `deepr/experts/` -- Domain expert system
- `deepr/mcp/` -- MCP server and tools
- `deploy/` -- Cloud deployment templates
- `deploy/aws/` -- AWS SAM/CloudFormation (Lambda, DynamoDB, Fargate)
- `deploy/azure/` -- Azure Bicep (Functions, Cosmos DB, Container Apps)
- `deploy/gcp/` -- GCP Terraform (Cloud Functions, Firestore, Cloud Run)
- `deploy/shared/` -- Shared API library (`deepr_api_common`)
- `tests/unit/` -- Unit tests
- `tests/integration/` -- Integration tests (require API keys)

## Guidelines

- Keep changes focused. One feature or fix per PR.
- Add tests for new functionality.
- Use structured logging (`logging.getLogger(__name__)`) in library code, not `print()`.
- Use specific exception types, not bare `except Exception`.
- Model pricing and capabilities go in `deepr/providers/registry.py` (single source of truth).
- Version is defined once in `deepr/__init__.py` and imported elsewhere.

## Cloud Deployment Guidelines

When modifying cloud handlers (`deploy/*/`):

- Use native cloud tooling: SAM for AWS, Bicep for Azure, Terraform for GCP.
- Validate input at the handler level (prompt length, model, job ID format).
- Include security headers (HSTS, X-Frame-Options, X-Content-Type-Options).
- Add CORS OPTIONS handling for browser clients.
- Use the shared library (`deploy/shared/deepr_api_common/`) for common utilities.
- Verify handler syntax with `python -m py_compile <handler.py>`.
- Test API key validation with both `Authorization: Bearer` and `X-Api-Key` headers.

## High-Impact Areas

The most valuable contributions are in: research quality (synthesis prompts, context chaining), provider integrations, cost optimization, and CLI usability. See [ROADMAP.md](ROADMAP.md) for planned work.

## Questions

Open an issue at [GitHub Issues](https://github.com/blisspixel/deepr/issues) or email nick@pueo.io.
