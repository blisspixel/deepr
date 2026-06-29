# MCP Integration Guide

**Status**: dynamic discovery, resource subscriptions, prompt templates, structured errors, structured JSON results

Deepr exposes research and expert capabilities via Model Context Protocol (MCP) for AI agents including OpenClaw, Claude Desktop, Cursor, VS Code, and Zed. For a no-surprise-cost agent test path, see [docs/MCP_AGENT_TEST_GUIDE.md](../docs/MCP_AGENT_TEST_GUIDE.md).

---

## For the consuming agent (start here)

If you are an agent that just connected, this is how to use Deepr well. The
design follows current MCP guidance: outcome-oriented tools, a free discovery
path, explicit cost tiers, and structured errors so you never have to guess or
loop.

**Orient first, for free.** `deepr_status` returns version, active jobs, and the
day/month cost summary. `deepr_list_experts` returns the roster (each expert is a
named domain role, not a generic search box). Both are `cost_tier: free`. Read
the tool's `cost_tier` before calling: `free` ($0), `low` (cents, owned/prepaid
capable), `medium`/`high` (metered, confirm budget first).

**Pick the smallest tool that gets the outcome:**
- One expert or many experts, no-metered trial -> `deepr_consult_experts`.
  Pass one name in `experts` for a one-expert consult, or pass several names for
  a council. Set `synthesis_backend: "local"` or `"plan"` and `budget: 0`.
- A cross-domain question -> `deepr_consult_experts`: it routes to the relevant
  experts (or pass `experts`), fans out up to `max_experts` (<=10), and returns
  one synthesized `deepr-consult-v1` artifact (answer, each expert's perspective
  with confidence, agreements, dissent, cost). One call, aggregated result.
- Legacy single-expert chat -> `deepr_query_expert`. This path is
  metered-capable, does not yet accept local or plan backend selection, and
  should only be used when the operator approves its budget.
- "What changed since I last asked?" -> `deepr_what_changed`; a handoff snapshot
  -> `deepr_expert_handoff`; why a claim is held -> `deepr_explain_belief`;
  related memory candidates -> `deepr_semantic_recall`; time-scoped edge
  qualifiers -> `deepr_temporal_edges`. All `$0`, read-only, versioned.
- A deep autonomous investigation -> `deepr_agentic_research` (Plan-Execute-Review,
  $1-$10; confirm budget with the human first).

**Spend $0 by default.** For cross-expert consults, pass
`synthesis_backend: "local"` (Ollama) or `"plan"` with `plan: "codex"` (also
claude/grok) to run synthesis on owned or prepaid capacity. In those modes Deepr
disables silent metered fallback, so a missing-context answer is an honest "no
context" rather than a surprise charge. Local and plan consults allow a zero
budget. API-backed consults require a positive budget. `deepr_query_expert` is
still the legacy chat path and does not yet accept local, plan, provider, or
model selection; treat it as metered-capable unless the operator approves it.

**Errors are structured, not prose.** A failed call returns
`{error_code, category, retryable, message}` (e.g. `CONSULT_BACKEND_UNAVAILABLE`,
`INVALID_BUDGET`). Branch on `error_code` and respect `retryable`; do not retry a
non-retryable error in a loop.

**Handoff is machine-validated.** Every artifact carries `schema_version` and
`kind`; JSON-object tool results also return MCP `structuredContent` while
retaining text JSON for older clients. Read those contracts instead of
pattern-matching prose. Deepr recommends and returns artifacts; your harness
decides and enacts. See [docs/MCP_AGENT_TEST_GUIDE.md](../docs/MCP_AGENT_TEST_GUIDE.md)
for a $0 end-to-end script.

**Validate before a real remote consult.** `deepr mcp smoke-http` proves
endpoint reachability and free tool dispatch. `deepr mcp validate-consult`
proves the no-metered expert consult contract through an offline fixture,
in-process live local or plan capacity, or a remote HTTP endpoint:

```bash
deepr mcp validate-consult --json
deepr mcp validate-consult --live --synthesis-backend local --expert "AI Agent Harnesses" --json
deepr mcp validate-consult http://127.0.0.1:8765/mcp --auth-token "$DEEPR_MCP_KEY" --expert "AI Agent Harnesses" --json
```

---

## Setup by Runtime

For no-metered local or LAN tests, remove provider API keys from the MCP server
environment in every template below. Use `deepr_consult_experts` with
`synthesis_backend="local"` or `synthesis_backend="plan"` and verify
`capacity.live_metered_fallback=false` plus `cost_usd=0`.

### OpenClaw

Copy `mcp/openclaw-config.json` to your OpenClaw MCP configuration:

```json
{
  "mcpServers": {
    "deepr-research": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "DEEPR_LOG_LEVEL": "INFO",
        "DEEPR_LOG_FORMAT": "json"
      },
      "autoAllow": [
        "deepr_tool_search", "deepr_status", "deepr_list_experts",
        "deepr_get_expert_info", "deepr_check_status", "deepr_get_result"
      ]
    }
  }
}
```

The `autoAllow` list includes read-only tools that don't incur costs. Cost-incurring tools (`deepr_research`, `deepr_agentic_research`, `deepr_query_expert`) require approval. For no-cost expert synthesis, use `deepr_consult_experts` with `synthesis_backend="local"` or `synthesis_backend="plan"` and verify `capacity.live_metered_fallback=false`.
For no-metered trials, omit provider API keys from the MCP server environment.

For Docker deployment, use `mcp/openclaw-docker-config.json` instead.

### Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).

Use the template from `mcp/mcp-config-claude-desktop.json`:

```json
{
  "mcpServers": {
    "deepr-research": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key-here"
      }
    }
  }
}
```

Restart Claude Desktop after saving.

### Cursor

Edit Cursor MCP settings. Use the template from `mcp/mcp-config-cursor.json` (same format as Claude Desktop).

### VS Code

Add to your VS Code MCP settings (`.vscode/mcp.json` or user settings). Use the template from `mcp/mcp-config-vscode.json`:

```json
{
  "servers": {
    "deepr-research": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key-here"
      }
    }
  }
}
```

### Zed

Add to `~/.config/zed/settings.json` under `"language_models"` -> `"mcp"`:

```json
{
  "language_models": {
    "mcp": {
      "deepr-research": {
        "command": "python",
        "args": ["-m", "deepr.mcp.server"],
        "env": {
          "OPENAI_API_KEY": "your-openai-key-here"
        }
      }
    }
  }
}
```

---

## Available Tools

### System Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_capabilities` | Discovery: versioned capability map (roster, key tools + cost tiers, $0 paths, error contract). Call first | Free |
| `deepr_tool_search` | Dynamic tool discovery via BM25 search | Free |
| `deepr_status` | Health check (version, uptime, active jobs, spending) | Free |

### Research Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_research` | Submit deep research job | $0.10-0.50 |
| `deepr_check_status` | Check job progress | Free |
| `deepr_get_result` | Get completed report | Free |
| `deepr_cancel_job` | Cancel running job | Free |
| `deepr_agentic_research` | Autonomous multi-step research | $1-10 |

### Expert Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_list_experts` | List domain experts | Free |
| `deepr_query_expert` | Legacy single-expert chat with a metered-capable backend; use only with operator-approved budget | Low |
| `deepr_consult_experts` | Consult one or more experts and synthesize a versioned `deepr-consult-v1` artifact; supports `synthesis_backend=local|plan` to avoid live metered fallback | Free to low |
| `deepr_get_expert_info` | Expert details and stats | Free |
| `deepr_expert_manifest` | Expert manifest (policy + knowledge snapshot) | Free |
| `deepr_expert_validate` | Validate a claim against expert knowledge (guardrail mode) | Low |
| `deepr_rank_gaps` | Rank an expert's knowledge gaps by value | Free |
| `deepr_expert_health_check` | Read-only knowledge-state audit (freshness, contradictions, provenance, gaps) | Free |
| `deepr_expert_loop_status` | Durable expert loop-run status, stop reasons, and next actions | Free |
| `deepr_semantic_recall` | Candidate belief recall for verifier or host-agent routing | Free |
| `deepr_expert_handoff` | Versioned read-only expert handoff payload for downstream agents | Free |
| `deepr_route_gaps` | Route an expert's gaps to the best fill instrument (recon/distillr/primr/research) | Free |
| `deepr_expert_absorb` | Promote a research report into expert beliefs, verification-gated (mutating) | Low |
| `deepr_reflect` | Self-evaluate a research report (grounding/completeness/calibration/directness) | Low |
| `deepr_what_changed` | Perspective delta since a timestamp (added/revised/contested/archived) | Free |
| `deepr_contested` | Open contradiction pairs with both sides' claims and provenance | Free |
| `deepr_explain_belief` | Why the expert believes something (evidence, history, support chains) | Free |
| `deepr_temporal_edges` | Temporal edge qualifiers filtered by valid or observed time | Free |

### Task Management Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_get_task_progress` | Progress of a durable task | Free |
| `deepr_list_recoverable_tasks` | List resumable tasks for a job | Free |
| `deepr_resume_task` | Resume an interrupted task | Varies |
| `deepr_pause_task` | Pause a running task | Free |

### Skill Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_list_skills` | List skills available to an expert | Free |
| `deepr_install_skill` | Install a skill into an expert | Free |

### Dynamic Discovery

Deepr uses a gateway pattern for context efficiency. By default, `tools/list` returns only `deepr_tool_search`. Agents search for capabilities by description:

```
deepr_tool_search(query="submit research job")  -> returns deepr_research schema
deepr_tool_search(query="expert knowledge")     -> returns expert tool schemas
```

This reduces initial context by ~85%.

---

## Resource URIs

Subscribe to resources for push notifications instead of polling (70% token savings):

### Campaign Resources (live)
| URI | Content |
|-----|---------|
| `deepr://campaigns/{id}/status` | Job phase, progress, cost |
| `deepr://campaigns/{id}/plan` | Research plan |
| `deepr://campaigns/{id}/beliefs` | Accumulated findings |

### Report Artifacts (completed)
| URI | Content |
|-----|---------|
| `deepr://reports/{id}/final.md` | Full research report |
| `deepr://reports/{id}/summary.json` | Report metadata |

### Log Artifacts (provenance)
| URI | Content |
|-----|---------|
| `deepr://logs/{id}/search_trace.json` | Search query history |
| `deepr://logs/{id}/decisions.md` | Decision log |

### Expert Resources (persistent)
| URI | Content |
|-----|---------|
| `deepr://experts/{id}/profile` | Expert metadata |
| `deepr://experts/{id}/beliefs` | Knowledge with confidence |
| `deepr://experts/{id}/gaps` | Known knowledge gaps |

---

## Prompt Templates

Three prompt templates available via `prompts/list`:

| Prompt | Description |
|--------|-------------|
| `deep_research_task` | Comprehensive research with executive summary |
| `expert_consultation` | Domain expert Q&A with gap handling |
| `comparative_analysis` | Multi-option comparison with decision matrix |

---

## Structured Errors

All tools return structured errors for agent retry/fallback:

```json
{
  "error_code": "BUDGET_EXCEEDED",
  "message": "Research blocked by cost safety: daily limit reached",
  "retry_hint": "Wait for daily limit reset",
  "fallback_suggestion": "Daily spent: $45.00"
}
```

Common error codes: `BUDGET_EXCEEDED`, `JOB_NOT_FOUND`, `EXPERT_NOT_FOUND`, `PROVIDER_NOT_CONFIGURED`, `BUDGET_INSUFFICIENT`, `EXPERT_REQUIRED`, `TOOL_NOT_FOUND`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for research |
| `XAI_API_KEY` | No | xAI/Grok API key |
| `GEMINI_API_KEY` | No | Google Gemini API key |
| `AZURE_OPENAI_API_KEY` | No | Azure OpenAI API key |
| `DEEPR_LOG_LEVEL` | No | Logging level (default: INFO) |
| `DEEPR_LOG_FORMAT` | No | `text` or `json` (default: text) |
| `DEEPR_MCP_KEYS_PATH` | No | Experimental scoped-key store for HTTP MCP auth; enables per-key mode, expert-scope, budget, and rate-limit checks before `tools/call` dispatch |
| `DEEPR_MCP_AUTH_TOKEN` | No | Shared-token fallback for HTTP MCP auth |

---

## Scoped HTTP Keys

Experimental HTTP MCP keys are local records used by the HTTP transport when
`DEEPR_MCP_KEYS_PATH` points at a key store:

```bash
deepr mcp keys create --mode read_only --expert "AI Strategy Expert" --rate-limit 30
deepr mcp keys list
deepr mcp keys revoke <key-id>
deepr mcp audit list
deepr mcp audit summary
```

Created secrets are shown once. `list` never prints secrets or stored hashes.
Scoped HTTP calls enforce the stored budget ceiling before dispatch from prior
audited spend and deterministic tool estimates. Metered tools without an
estimate are denied before handler dispatch. Scoped HTTP calls also enforce the
optional per-key calls-per-minute limit from recent audited calls, return retry
metadata on rate-limit denials, and write successful response costs back to the
remote audit log. `deepr mcp audit list` reads that local append-only audit log
with optional `--key-id`, `--tool`, `--outcome`, `--limit`, and `--json`
filters.
`deepr mcp audit summary` aggregates the same records by key, tool, and outcome.
HTTP POST concurrency is capped at 32 by default. Override it with
`DEEPR_MCP_HTTP_MAX_CONCURRENCY` or `deepr mcp serve --http --max-concurrency`.

To create a trial key and a copy-ready handoff for another agent, use:

```bash
deepr mcp agent-guide --host 0.0.0.0 --public-host 192.168.44.62 --key-id agent-trial --budget 0 --rate-limit 30
```

The guide includes the server command, endpoint, bearer token, allowed tool
rules, and a no-metered `deepr_consult_experts` example. Use `--expert "Name"`
once for a single-expert consult or repeat it for a fixed expert council. Use
`--synthesis-backend plan --plan codex` for an explicit plan-capacity consult,
or `--output data/security/agent-guide.md` to write a file. Because the guide
contains a bearer token, repo-local output paths must be git-ignored unless
`--allow-tracked-output` is passed intentionally.

## HTTP Serve Mode

Stdio remains the default MCP transport. For a remote-capable local endpoint,
run the same server over Streamable HTTP:

```bash
deepr mcp keys create --mode read_only --rate-limit 30 --keys-path data/security/mcp_keys.json
deepr mcp serve --http --host 127.0.0.1 --port 8765 --max-concurrency 32 --keys-path data/security/mcp_keys.json
```

The HTTP listener binds to loopback by default. A reachable bind such as
`--host 0.0.0.0` must have a shared token or at least one active scoped key,
otherwise startup is refused.

### Reaching experts from another machine on your LAN

An agent on a different machine on the same network can consult your experts.
Bind to a reachable interface with auth, then point the agent at this host's LAN
IP:

```bash
# On the host that has the experts (find its LAN IP, e.g. 192.168.44.62):
deepr mcp serve --http --host 0.0.0.0 --port 8765 --auth-token "$DEEPR_MCP_TOKEN"

# From the other machine (or to validate locally over the LAN IP):
deepr mcp smoke-http http://192.168.44.62:8765/mcp --auth-token "$DEEPR_MCP_TOKEN"
```

Validated 2026-06-25: the LAN-IP endpoint with the token passes health,
initialize, tools/list, and tools/call; the same endpoint **without** the token
is rejected `Unauthorized` on every call except the unauthenticated health ping.
Two operational notes: open the chosen port in the host firewall (Windows will
prompt on first bind), and prefer scoped keys (`--keys-path`) over a shared
`--auth-token` so you can scope an agent to specific experts and a budget and
revoke it independently. For anything beyond a trusted LAN, terminate TLS at a
reverse proxy (see [deploy/mcp-http.md](../deploy/mcp-http.md)) rather than
exposing plaintext HTTP.

Validate a local or proxied endpoint without provider calls:

```bash
deepr mcp smoke-http http://127.0.0.1:8765/mcp
deepr mcp smoke-http https://mcp.example.com/mcp --auth-token "$DEEPR_MCP_KEY"
deepr mcp validate-consult https://mcp.example.com/mcp --auth-token "$DEEPR_MCP_KEY" --expert "AI Agent Harnesses" --json
```

For remote host setup, emit a token-redacted registration manifest after the
same `$0` smoke checks pass:

```bash
deepr mcp registration-manifest https://mcp.example.com/mcp \
  --auth-token "$DEEPR_MCP_KEY" \
  --agent-name planner \
  --output mcp-registration.json
```

The manifest uses `deepr-mcp-registration-manifest-v1`, includes endpoint,
auth-header, scoped-key, audit-schema, and smoke-result metadata, and never
serializes the bearer token itself. Use `--skip-smoke` only to draft a manifest
before the endpoint is reachable.

For a hosted reverse-proxy recipe with TLS and scoped-key guidance, see
[deploy/mcp-http.md](../deploy/mcp-http.md). For a repeatable containerized
local service, use [deploy/mcp-http/](../deploy/mcp-http/) and bootstrap a
scoped key before `docker compose up`.

---

## Architecture

```
StdioServer (JSON-RPC transport)
    -> Method dispatch (initialize, tools/*, resources/*, prompts/*)
        -> DeeprMCPServer (business logic)
            -> MCPResourceHandler (resource reads, subscriptions)
            -> JobManager (job lifecycle, notifications)
            -> GatewayTool + ToolRegistry (BM25 dynamic discovery)
            -> ResearchOrchestrator (research execution)
            -> ExpertStore (expert management)
```

**Transport**: stdio (JSON-RPC 2.0 over stdin/stdout)
**Job Tracking**: In-memory with SQLite persistence (`data/mcp_jobs.db`)
**Logging**: Structured JSON to stderr (for OpenClaw log aggregation)

---

## Troubleshooting

**Server not starting:**
- Verify Python 3.12+: `python --version`
- Verify Deepr installed: `pip show deepr` or `deepr --version`
- Try absolute Python path in config
- Check logs in your runtime (Claude Desktop: Help -> View Logs)

**API key issues:**
- Verify key in config JSON (no extra quotes/spaces)
- For OpenClaw, use `${OPENAI_API_KEY}` syntax for env injection
- Test with `deepr doctor` from CLI

**"No tools found":**
- Deepr uses dynamic discovery. Ask: "Search for research tools" to trigger `deepr_tool_search`
- Or use `deepr_status` to verify the server is running

**Job not found after restart:**
- Jobs are persisted in SQLite but provider instances are lost
- Check `data/mcp_jobs.db` for job history
- Re-submit if needed

---

**Tools:** 32 (3 system + 5 research + 18 expert + 4 task management + 2 skills)
**Resources:** 10 URI schemes across 4 resource types
**Prompts:** 3 templates
