# Testing summary

Deepr's blocking release signal is the complete provider-free unit suite:

```bash
pytest tests/unit/ --ignore=tests/data -q
```

CI runs on Python 3.12, 3.13, and 3.14, enforces at least 80% branch coverage,
and runs lint, format, strict mypy islands, documentation consistency, package,
frontend, file-size, security/complexity, secret-history, and dependency gates.

Every bug fix adds a regression test. Provider clients, external tools, local
hardware, time, storage, and ledgers are mocked or isolated unless a test is
explicitly outside `tests/unit/`.

Live integration tests are manual opt-in only. They require explicit user
authorization, a cost estimate and ceiling, isolated state, and bounded cleanup.
They are never a substitute for deterministic unit coverage and never run in
the default CI scope.

Historical low-cost keyboard expert scripts were removed. Their fixed prices,
API creation flow, hosted vectors, and metered chat assumptions no longer match
the v2.36 fail-closed contracts.
