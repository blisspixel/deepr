# Deepr test suite

## Release-safe command

Install the complete test dependencies, then run the exact CI unit scope:

```bash
uv pip install -e ".[dev,full]"
pytest tests/unit/ --ignore=tests/data -q
```

The unit suite must pass with no provider keys and no `.env`. It blocks outbound
network access except loopback fixtures, contains 8,000+ test functions, and
enforces at least 80% branch coverage in CI.

Do not run bare `pytest`. `tests/integration/` contains explicit live-provider
tests, fails without credentials, can spend money, and includes long polling
paths. No integration or E2E command is part of the normal release gate.

## Focused expert checks

```bash
pytest tests/unit/test_experts/ -q
pytest tests/unit/test_cli/test_expert_commands.py -q
pytest tests/unit/test_mcp/test_consult_tool.py -q
pytest tests/unit/test_eval/test_deliberation_eval.py -q
```

These use mocks, frozen fixtures, local files, or `$0` evaluation logic. They do
not create live provider experts or mutate a developer's expert library.

## Live validation policy

Run a live provider or external-tool test only after the user explicitly asks,
the exact cost is estimated, a positive ceiling is approved, and the test owns
isolated data and cleanup. v2.36-gated metered expert chat, lifecycle,
benchmark, hosted-context, batch, campaign, team, and agentic surfaces are not
valid live test targets.

See [TEST_EXPERT_CREATION.md](TEST_EXPERT_CREATION.md) for current provider-free
expert creation checks and [TESTING_SUMMARY.md](TESTING_SUMMARY.md) for the
release gate summary.
