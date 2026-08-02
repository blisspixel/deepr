"""Render the operator/agent trial guide for ``deepr mcp agent-guide``."""

from __future__ import annotations

import json


def normalize_mcp_path(path: str) -> str:
    resolved = path.strip() or "/mcp"
    return resolved if resolved.startswith("/") else f"/{resolved}"


def build_agent_guide_text(
    *,
    endpoint: str,
    token: str,
    key_id: str | None,
    bind_host: str,
    port: int,
    http_path: str,
    keys_path: str,
    mode: str,
    budget: float | None,
    rate_limit: int | None,
    experts: tuple[str, ...],
    synthesis_backend: str,
    plan: str | None,
) -> str:
    """Return the redacted or live agent trial guide body."""
    arguments: dict[str, object] = {
        "_approved": True,
        "question": "What should the current project do next?",
        "max_experts": 3,
        "synthesis_backend": synthesis_backend,
        "budget": 0,
    }
    if experts:
        arguments["experts"] = list(experts)
    if synthesis_backend == "plan" and plan:
        arguments["plan"] = plan
    consult_call = {"name": "deepr_consult_experts", "arguments": arguments}

    list_step = (
        f"2. Use only these experts: {', '.join(experts)}."
        if experts
        else "2. Call deepr_list_experts and select one to three relevant experts."
    )
    info_step = (
        "3. Call deepr_get_expert_info for one allowed expert with _approved=true."
        if experts
        else "3. Call deepr_get_expert_info for at least one selected expert with _approved=true."
    )
    key_line = f"Key id: {key_id}" if key_id else "Key id: shared token"
    budget_line = "none" if budget is None else f"${budget:.2f}"
    rate_line = "none" if rate_limit is None else f"{rate_limit}/minute"
    normalized_path = normalize_mcp_path(http_path)

    return f"""# Deepr MCP Agent Trial

## Operator

Run this on the machine that owns the Deepr experts:

```powershell
cd C:\\GitHub\\deepr
# Offline dual-era host-interop proof ($0, no network, no model)
.\\.venv\\Scripts\\deepr.exe mcp conformance --json
$env:DEEPR_MCP_KEYS_PATH = "{keys_path}"
.\\.venv\\Scripts\\deepr.exe mcp serve --http --host {bind_host} --port {port} --path {normalized_path} --keys-path $env:DEEPR_MCP_KEYS_PATH
```

Remote smoke is intentionally fail-closed until cost authority is proven:

```powershell
.\\.venv\\Scripts\\deepr.exe mcp smoke-http {endpoint} --auth-token "{token}"
```

Expected: blocked report with network_opened=false (not a green remote probe).

Scoped key:

```text
{key_line}
Mode: {mode}
Budget: {budget_line}
Rate limit: {rate_line}
Token: {token}
```

## Agent Instructions

Connect to:

```text
{endpoint}
```

Use this HTTP header:

```text
Authorization: Bearer {token}
```

Rules:

1. First call deepr_tool_search with query "expert list handoff consult".
{list_step}
{info_step}
4. Prefer deepr_expert_handoff for context. Include _approved=true.
5. Prefer deepr_consult_experts for questions. Use one expert for focused advice or multiple experts for council guidance. Include _approved=true.
6. Do not call deepr_query_expert, deepr_research, deepr_agentic_research, deepr_expert_absorb, deepr_reflect, deepr_install_skill, or mutating tools.
7. For consults, force no-metered execution with synthesis_backend="{synthesis_backend}" and budget=0.
8. Verify capacity.live_metered_fallback=false and cost_usd=0.
9. If local or plan synthesis is unavailable, return the structured error. Do not retry with API or metered fallback.
10. Preserve expert disagreement and uncertainty in your consolidated guidance. Deepr experts are perspectives, not a fact list.

Example consult call:

```json
{json.dumps(consult_call, indent=2)}
```
"""
