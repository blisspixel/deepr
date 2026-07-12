# Expert test guide

Use provider-free unit tests and frozen fixtures for expert behavior:

```bash
pytest tests/unit/test_experts/ -q
pytest tests/unit/test_cli/test_expert_commands.py -q
pytest tests/unit/test_cli/test_expert_consult.py -q
pytest tests/unit/test_mcp/test_query_expert_tool.py -q
pytest tests/unit/test_mcp/test_consult_tool.py -q
```

The tests cover structured state, confidence/trust floors, contradiction and
gap handling, local/plan capacity gates, consult traces, dissent, exact council
settlement, derived views, and fail-closed metered surfaces. They must not depend
on a developer's `.env`, live expert library, Ollama availability, or provider
accounts.

For optional local hardware dogfood, use explicit local commands against an
isolated expert root. A scheduled `busy` result is valid and should record retry
guidance instead of falling through to paid capacity.

Standalone metered expert chat, API lifecycle mutation, live provider
benchmarks, and agentic multi-round research are gated in v2.36 and are not
manual acceptance tests. A larger budget does not unlock them.
