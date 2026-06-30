"""MCP (Model Context Protocol) server commands."""

import sys

import click

from deepr.cli.async_runner import run_async_command
from deepr.cli.commands.mcp_consult_validation import validate_consult_fleet


@click.group()
def mcp():
    """Model Context Protocol server for AI agent integration."""
    pass


mcp.add_command(validate_consult_fleet)


@mcp.group()
def keys():
    """Manage experimental scoped API keys for HTTP MCP access."""
    pass


@mcp.group()
def audit():
    """Review append-only HTTP MCP remote-call audit records."""
    pass


def _load_key_store(keys_path: str | None):
    from pathlib import Path

    from deepr.mcp.security.scoped_keys import ScopedMCPKeyStore

    return ScopedMCPKeyStore(Path(keys_path)) if keys_path else ScopedMCPKeyStore()


def _load_remote_audit_log(audit_path: str | None):
    from pathlib import Path

    from deepr.mcp.security.scoped_keys import RemoteMCPAuditLog

    return RemoteMCPAuditLog(Path(audit_path)) if audit_path else RemoteMCPAuditLog()


def _key_record_payload(record, *, include_secret: str | None = None):
    payload = record.to_dict(include_secret_hash=False)
    if include_secret is not None:
        payload["secret"] = include_secret
    return payload


def _audit_record_payload(record):
    return record.to_dict()


def _format_audit_cost(cost_usd: float | None) -> str:
    return "none" if cost_usd is None else f"${cost_usd:.4f}"


def _normalize_mcp_path(path: str) -> str:
    resolved = path.strip() or "/mcp"
    return resolved if resolved.startswith("/") else f"/{resolved}"


def _resolve_agent_endpoint(
    *,
    endpoint: str | None,
    public_host: str | None,
    bind_host: str,
    port: int,
    http_path: str,
) -> str:
    if endpoint:
        return endpoint.rstrip("/")
    host = public_host or bind_host
    return f"http://{host}:{port}{_normalize_mcp_path(http_path)}"


def _nearest_existing_parent(path):
    from pathlib import Path

    current = Path(path).resolve()
    if current.is_file():
        current = current.parent
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _git_command(args: list[str], *, cwd):
    import shutil
    import subprocess

    git_exe = shutil.which("git")
    if git_exe is None:
        return None
    return subprocess.run(  # noqa: S603 - fixed git executable, no shell, internal metadata probes.
        [git_exe, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_worktree_root(path) -> str | None:
    probe_dir = _nearest_existing_parent(path)
    result = _git_command(["rev-parse", "--show-toplevel"], cwd=probe_dir)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _path_requires_git_ignore(path) -> bool:
    from pathlib import Path

    output_path = Path(path).resolve()
    root_raw = _git_worktree_root(output_path)
    if not root_raw:
        return False
    root = Path(root_raw).resolve()
    try:
        relative = output_path.relative_to(root)
    except ValueError:
        return False

    relative_arg = relative.as_posix()
    tracked = _git_command(["ls-files", "--error-unmatch", "--", relative_arg], cwd=root)
    if tracked is not None and tracked.returncode == 0:
        return True
    ignored = _git_command(["check-ignore", "--quiet", "--", relative_arg], cwd=root)
    return ignored is None or ignored.returncode != 0


def _validate_agent_guide_output_path(output: str | None, *, allow_tracked_output: bool) -> None:
    if not output or allow_tracked_output:
        return
    if _path_requires_git_ignore(output):
        raise click.ClickException(
            "Refusing to write a bearer-token MCP guide to a tracked or unignored git path. "
            "Use an ignored path such as data/security/agent-guide.md, or pass "
            "--allow-tracked-output if this is intentional."
        )


def _build_agent_guide_text(
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
    import json

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
    normalized_path = _normalize_mcp_path(http_path)

    return f"""# Deepr MCP Agent Trial

## Operator

Run this on the machine that owns the Deepr experts:

```powershell
cd C:\\GitHub\\deepr
$env:DEEPR_MCP_KEYS_PATH = "{keys_path}"
.\\.venv\\Scripts\\deepr.exe mcp serve --http --host {bind_host} --port {port} --path {normalized_path} --keys-path $env:DEEPR_MCP_KEYS_PATH
```

Smoke test:

```powershell
.\\.venv\\Scripts\\deepr.exe mcp smoke-http {endpoint} --auth-token "{token}"
```

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


def _redact_agent_guide_secret(guide: str, token: str) -> str:
    return guide.replace(token, "<redacted-token>") if token else guide


def _filter_audit_records(records, *, key_id: str | None, tool_name: str | None, outcome: str | None):
    filtered = records
    if key_id:
        filtered = [record for record in filtered if record.key_id == key_id]
    if tool_name:
        filtered = [record for record in filtered if record.tool == tool_name]
    if outcome:
        filtered = [record for record in filtered if record.outcome == outcome]
    return filtered


def _summarize_audit_records(records) -> dict:
    def empty_bucket() -> dict:
        return {"count": 0, "cost_usd": 0.0}

    summary: dict = {
        "count": len(records),
        "cost_usd": 0.0,
        "costed_records": 0,
        "by_key": {},
        "by_tool": {},
        "by_outcome": {},
    }
    for record in records:
        cost = float(record.cost_usd or 0.0)
        if record.cost_usd is not None:
            summary["costed_records"] += 1
        summary["cost_usd"] += cost
        for group_name, group_key in (
            ("by_key", record.key_id),
            ("by_tool", record.tool),
            ("by_outcome", record.outcome),
        ):
            bucket = summary[group_name].setdefault(group_key, empty_bucket())
            bucket["count"] += 1
            bucket["cost_usd"] += cost
    summary["cost_usd"] = round(summary["cost_usd"], 10)
    for group_name in ("by_key", "by_tool", "by_outcome"):
        summary[group_name] = {
            key: {"count": value["count"], "cost_usd": round(value["cost_usd"], 10)}
            for key, value in sorted(
                summary[group_name].items(),
                key=lambda item: (-item[1]["count"], item[0]),
            )
        }
    return summary


@keys.command("create")
@click.option("--key-id", help="Stable key id. Defaults to a generated id.")
@click.option(
    "--mode",
    type=click.Choice(["read_only", "standard", "extended", "unrestricted"], case_sensitive=False),
    default="read_only",
    show_default=True,
    help="ResearchMode applied to remote tool calls made with this key.",
)
@click.option("--expert", "experts", multiple=True, help="Restrict this key to one expert. Repeatable.")
@click.option("--budget", type=click.FloatRange(min=0.0), help="Per-key budget ceiling metadata in USD.")
@click.option("--rate-limit", type=click.IntRange(min=1), help="Maximum HTTP MCP tool calls per minute for this key.")
@click.option("--keys-path", type=click.Path(dir_okay=False, path_type=str), help="Override key-store path.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def create_key(
    key_id: str | None,
    mode: str,
    experts: tuple[str, ...],
    budget: float | None,
    rate_limit: int | None,
    keys_path: str | None,
    as_json: bool,
):
    """Create a scoped HTTP MCP key and print the secret once."""
    import json

    from deepr.mcp.security.tool_allowlist import ResearchMode

    try:
        secret, record = _load_key_store(keys_path).create_key(
            key_id,
            mode=ResearchMode(mode.lower()),
            expert_allowlist=experts,
            budget_limit_usd=budget,
            rate_limit_per_minute=rate_limit,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    payload = _key_record_payload(record, include_secret=secret)
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    click.echo(f"Created MCP key: {record.key_id}")
    click.echo(f"Mode: {record.mode.value}")
    if record.expert_allowlist:
        click.echo(f"Experts: {', '.join(record.expert_allowlist)}")
    if record.budget_limit_usd is not None:
        click.echo(f"Budget ceiling: ${record.budget_limit_usd:.2f}")
    if record.rate_limit_per_minute is not None:
        click.echo(f"Rate limit: {record.rate_limit_per_minute}/minute")
    click.echo("")
    click.echo("Secret, shown once:")
    click.echo(secret)


@keys.command("list")
@click.option("--keys-path", type=click.Path(dir_okay=False, path_type=str), help="Override key-store path.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def list_keys(keys_path: str | None, as_json: bool):
    """List scoped HTTP MCP keys without revealing secrets."""
    import json

    records = _load_key_store(keys_path).list_keys()
    payload = [_key_record_payload(record) for record in records]
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    if not records:
        click.echo("No MCP keys found.")
        return
    for record in records:
        status = "revoked" if record.revoked else "active"
        experts = ", ".join(record.expert_allowlist) if record.expert_allowlist else "all"
        last_used = record.last_used_at.isoformat() if record.last_used_at else "never"
        budget = f"${record.budget_limit_usd:.2f}" if record.budget_limit_usd is not None else "none"
        rate_limit = f"{record.rate_limit_per_minute}/min" if record.rate_limit_per_minute is not None else "none"
        click.echo(
            f"{record.key_id}\t{status}\tmode={record.mode.value}\texperts={experts}\tbudget={budget}\t"
            f"rate_limit={rate_limit}\tlast_used={last_used}"
        )


@keys.command("revoke")
@click.argument("key_id")
@click.option("--keys-path", type=click.Path(dir_okay=False, path_type=str), help="Override key-store path.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def revoke_key(key_id: str, keys_path: str | None, as_json: bool):
    """Revoke a scoped HTTP MCP key."""
    import json

    changed = _load_key_store(keys_path).revoke(key_id)
    payload = {"key_id": key_id, "revoked": changed}
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    if not changed:
        raise click.ClickException(f"MCP key not found or already revoked: {key_id}")
    click.echo(f"Revoked MCP key: {key_id}")


@audit.command("list")
@click.option("--audit-path", type=click.Path(dir_okay=False, path_type=str), help="Override remote audit JSONL path.")
@click.option("--key-id", help="Show records for one scoped key id.")
@click.option("--tool", "tool_name", help="Show records for one MCP tool name.")
@click.option("--outcome", help="Show records for one outcome, such as success or error.")
@click.option(
    "--limit", default=20, show_default=True, type=click.IntRange(min=1, max=1000), help="Max records to show."
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def list_audit(
    audit_path: str | None,
    key_id: str | None,
    tool_name: str | None,
    outcome: str | None,
    limit: int,
    as_json: bool,
):
    """List scoped HTTP MCP remote-call audit records."""
    import json

    audit_log = _load_remote_audit_log(audit_path)
    records = _filter_audit_records(
        audit_log.read_recent(limit=1_000_000),
        key_id=key_id,
        tool_name=tool_name,
        outcome=outcome,
    )[-limit:]
    payload = {
        "audit_path": str(audit_log.path),
        "filters": {
            "key_id": key_id,
            "tool": tool_name,
            "outcome": outcome,
            "limit": limit,
        },
        "count": len(records),
        "events": [_audit_record_payload(record) for record in records],
    }
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    if not records:
        click.echo(f"No MCP remote audit records found at {audit_log.path}.")
        return
    click.echo(f"MCP remote audit records: {audit_log.path}")
    click.echo("timestamp\tkey_id\tmode\toutcome\ttool\tcost\texperts\terror_code\ttrace_id")
    for record in records:
        experts = ",".join(record.expert_names) if record.expert_names else "-"
        error_code = record.error_code or "-"
        trace_id = record.trace_id or "-"
        click.echo(
            f"{record.timestamp.isoformat()}\t{record.key_id}\t{record.mode.value}\t{record.outcome}\t"
            f"{record.tool}\t{_format_audit_cost(record.cost_usd)}\t{experts}\t{error_code}\t{trace_id}"
        )


@audit.command("summary")
@click.option("--audit-path", type=click.Path(dir_okay=False, path_type=str), help="Override remote audit JSONL path.")
@click.option("--key-id", help="Summarize records for one scoped key id.")
@click.option("--tool", "tool_name", help="Summarize records for one MCP tool name.")
@click.option("--outcome", help="Summarize records for one outcome, such as success or error.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def summarize_audit(
    audit_path: str | None,
    key_id: str | None,
    tool_name: str | None,
    outcome: str | None,
    as_json: bool,
):
    """Summarize scoped HTTP MCP remote-call audit records."""
    import json

    audit_log = _load_remote_audit_log(audit_path)
    records = _filter_audit_records(
        audit_log.read_recent(limit=1_000_000),
        key_id=key_id,
        tool_name=tool_name,
        outcome=outcome,
    )
    summary = _summarize_audit_records(records)
    payload = {
        "audit_path": str(audit_log.path),
        "filters": {
            "key_id": key_id,
            "tool": tool_name,
            "outcome": outcome,
        },
        "summary": summary,
    }
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    click.echo(f"MCP remote audit summary: {audit_log.path}")
    click.echo(f"Records: {summary['count']}")
    click.echo(f"Audited cost: {_format_audit_cost(summary['cost_usd'])}")
    click.echo(f"Records with cost: {summary['costed_records']}")
    for title, key in (("By outcome", "by_outcome"), ("By key", "by_key"), ("By tool", "by_tool")):
        click.echo(title + ":")
        if not summary[key]:
            click.echo("  none\t0\t$0.0000")
            continue
        for name, bucket in summary[key].items():
            click.echo(f"  {name}\t{bucket['count']}\t{_format_audit_cost(bucket['cost_usd'])}")


@mcp.command("agent-guide")
@click.option("--endpoint", help="Full MCP endpoint to give the remote agent. Overrides --public-host.")
@click.option("--public-host", help="Host or LAN IP the remote agent should use.")
@click.option("--host", "bind_host", default="127.0.0.1", show_default=True, help="HTTP host for the server command.")
@click.option("--port", default=8765, show_default=True, type=click.IntRange(min=1, max=65535), help="HTTP port.")
@click.option("--path", "http_path", default="/mcp", show_default=True, help="HTTP MCP path.")
@click.option("--keys-path", type=click.Path(dir_okay=False, path_type=str), default="data/security/mcp_keys.json")
@click.option("--key-id", help="Stable scoped key id. Defaults to a generated id.")
@click.option(
    "--mode",
    type=click.Choice(["read_only", "standard", "extended", "unrestricted"], case_sensitive=False),
    default="standard",
    show_default=True,
    help="Scoped-key mode. Standard is needed for approved expert handoff and consult calls.",
)
@click.option("--budget", type=click.FloatRange(min=0.0), default=0.0, show_default=True)
@click.option("--rate-limit", type=click.IntRange(min=1), default=30, show_default=True)
@click.option("--expert", "experts", multiple=True, help="Restrict this key to one expert. Repeatable.")
@click.option("--auth-token", help="Use an existing bearer token instead of creating a scoped key.")
@click.option("--no-create-key", is_flag=True, help="Do not create a key; requires --auth-token.")
@click.option(
    "--synthesis-backend",
    type=click.Choice(["local", "plan"], case_sensitive=False),
    default="local",
    show_default=True,
    help="No-metered consult backend to instruct the agent to use.",
)
@click.option("--plan", help="Plan id when --synthesis-backend=plan, such as codex or claude.")
@click.option("--output", type=click.Path(dir_okay=False, path_type=str), help="Write the guide to a file.")
@click.option(
    "--allow-tracked-output",
    is_flag=True,
    help="Allow writing the bearer-token guide to a tracked or unignored git path.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON with the guide text.")
def agent_guide(
    endpoint: str | None,
    public_host: str | None,
    bind_host: str,
    port: int,
    http_path: str,
    keys_path: str,
    key_id: str | None,
    mode: str,
    budget: float,
    rate_limit: int,
    experts: tuple[str, ...],
    auth_token: str | None,
    no_create_key: bool,
    synthesis_backend: str,
    plan: str | None,
    output: str | None,
    allow_tracked_output: bool,
    as_json: bool,
):
    """Create a scoped MCP trial key and print remote-agent instructions."""
    import json
    from pathlib import Path

    from deepr.mcp.security.tool_allowlist import ResearchMode

    normalized_path = _normalize_mcp_path(http_path)
    resolved_endpoint = _resolve_agent_endpoint(
        endpoint=endpoint,
        public_host=public_host,
        bind_host=bind_host,
        port=port,
        http_path=normalized_path,
    )
    _validate_agent_guide_output_path(output, allow_tracked_output=allow_tracked_output)
    if as_json and output is None and auth_token is None:
        raise click.ClickException(
            "JSON output redacts bearer tokens. Omit --json or pass --output to an ignored path "
            "to receive the one-time token."
        )
    token = auth_token
    record_id = key_id
    if no_create_key and not token:
        raise click.ClickException("--no-create-key requires --auth-token")
    if token is None:
        try:
            token, record = _load_key_store(keys_path).create_key(
                key_id,
                mode=ResearchMode(mode.lower()),
                expert_allowlist=experts,
                budget_limit_usd=budget,
                rate_limit_per_minute=rate_limit,
            )
        except Exception as exc:
            raise click.ClickException(str(exc)) from exc
        record_id = record.key_id
    if synthesis_backend.lower() == "plan" and not plan:
        plan = "codex"

    guide = _build_agent_guide_text(
        endpoint=resolved_endpoint,
        token=token,
        key_id=record_id,
        bind_host=bind_host,
        port=port,
        http_path=normalized_path,
        keys_path=keys_path,
        mode=mode.lower(),
        budget=budget,
        rate_limit=rate_limit,
        experts=experts,
        synthesis_backend=synthesis_backend.lower(),
        plan=plan,
    )
    payload = {
        "schema_version": "deepr-mcp-agent-guide-v1",
        "endpoint": resolved_endpoint,
        "key_id": record_id,
        "mode": mode.lower(),
        "budget_limit_usd": budget,
        "rate_limit_per_minute": rate_limit,
        "expert_allowlist": list(experts),
        "token_included": False,
        "server_command": (
            f".\\.venv\\Scripts\\deepr.exe mcp serve --http --host {bind_host} --port {port} "
            f"--path {normalized_path} --keys-path {keys_path}"
        ),
        "guide": _redact_agent_guide_secret(guide, token),
    }
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(guide, encoding="utf-8")
        if not as_json:
            click.echo(f"Wrote MCP agent guide: {output}")
            return
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        click.echo(guide, nl=False)


@mcp.command()
@click.option("--http", "use_http", is_flag=True, help="Serve MCP over Streamable HTTP instead of stdio.")
@click.option("--host", default="127.0.0.1", show_default=True, help="HTTP host to bind when --http is set.")
@click.option("--port", default=8765, show_default=True, type=click.IntRange(min=1, max=65535), help="HTTP port.")
@click.option("--path", "http_path", default="/mcp", show_default=True, help="HTTP MCP path.")
@click.option("--auth-token", help="Shared HTTP auth token. Scoped keys are preferred for production.")
@click.option(
    "--keys-path", type=click.Path(dir_okay=False, path_type=str), help="Scoped-key store path for HTTP auth."
)
@click.option(
    "--max-concurrency",
    "max_concurrent_requests",
    type=click.IntRange(min=1),
    help="Maximum simultaneous HTTP POST requests before returning 429.",
)
@click.option(
    "--allow-unauthenticated-public-bind",
    is_flag=True,
    help="Allow public HTTP bind without a token or scoped key. Unsafe outside isolated tests.",
)
def serve(
    use_http: bool,
    host: str,
    port: int,
    http_path: str,
    auth_token: str | None,
    keys_path: str | None,
    max_concurrent_requests: int | None,
    allow_unauthenticated_public_bind: bool,
):
    """Start MCP server for AI agent integration.

    The MCP server exposes Deepr experts via stdin/stdout protocol,
    allowing AI agents like Claude Desktop and Cursor to chat with
    your domain experts.

    Usage:
        deepr mcp serve

    Configuration:
        Add to Claude Desktop config (claude_desktop_config.json):
        {
          "mcpServers": {
            "deepr-experts": {
              "command": "python",
              "args": ["-m", "deepr.mcp.server"],
              "env": {
                "OPENAI_API_KEY": "sk-..."
              }
            }
          }
        }

    Then restart Claude Desktop and ask:
        "List my Deepr experts"
        "Ask my Azure Architect expert about Landing Zones"
    """
    try:
        if use_http:
            from deepr.mcp.http_server import run_http_server

            click.echo(f"Starting Deepr MCP HTTP Server at http://{host}:{port}{http_path}")
            click.echo("Press Ctrl+C to stop")
            click.echo("")
            run_async_command(
                run_http_server(
                    host=host,
                    port=port,
                    path=http_path,
                    auth_token=auth_token,
                    keys_path=keys_path,
                    max_concurrent_requests=max_concurrent_requests,
                    allow_unauthenticated_public_bind=allow_unauthenticated_public_bind,
                )
            )
            return

        # Import and run server
        from deepr.mcp.server import main as run_server

        click.echo("Starting Deepr MCP Server...")
        click.echo("AI agents can now access your experts via MCP protocol")
        click.echo("Press Ctrl+C to stop")
        click.echo("")

        run_server()

    except KeyboardInterrupt:
        click.echo("\nMCP server stopped")
    except Exception as e:
        click.echo(f"Error starting MCP server: {e}", err=True)
        sys.exit(1)


@mcp.command("smoke-http")
@click.argument("url")
@click.option("--auth-token", help="Bearer token or scoped-key secret for the HTTP MCP endpoint.")
@click.option("--timeout", "timeout_seconds", default=10.0, show_default=True, type=click.FloatRange(min=0.1))
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def smoke_http(url: str, auth_token: str | None, timeout_seconds: float, as_json: bool):
    """Smoke-test a Deepr HTTP MCP endpoint without provider calls."""
    import json

    from deepr.mcp.smoke import run_http_smoke

    try:
        report = run_async_command(
            run_http_smoke(
                url,
                auth_token=auth_token,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        click.echo(f"MCP HTTP smoke test: {report.url}")
        for step in report.steps:
            state = "ok" if step.ok else "fail"
            click.echo(f"[{state}] {step.name}: {step.detail}")
        click.echo("Result: passed" if report.ok else "Result: failed")

    if not report.ok:
        sys.exit(1)


@mcp.command("validate-consult")
@click.argument("url", required=False)
@click.option("--auth-token", help="Bearer token or scoped-key secret for a remote HTTP MCP endpoint.")
@click.option(
    "--live",
    is_flag=True,
    help="Run an in-process live consult when URL is omitted. Without this, URL-less mode uses an offline fixture.",
)
@click.option(
    "--synthesis-backend",
    type=click.Choice(["local", "plan"], case_sensitive=False),
    default="local",
    show_default=True,
    help="No-metered consult backend to validate.",
)
@click.option("--local-model", help="Optional Ollama model when --synthesis-backend=local.")
@click.option("--plan", help="Explicit plan id when --synthesis-backend=plan, such as codex or claude.")
@click.option("--plan-model", help="Optional model hint for the plan-quota CLI.")
@click.option("--expert", "experts", multiple=True, help="Expert to target. Repeatable.")
@click.option(
    "--question",
    default=None,
    help="Validation consult question. Defaults to a contract-focused prompt.",
)
@click.option("--timeout", "timeout_seconds", default=60.0, show_default=True, type=click.FloatRange(min=0.1))
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def validate_consult(
    url: str | None,
    auth_token: str | None,
    live: bool,
    synthesis_backend: str,
    local_model: str | None,
    plan: str | None,
    plan_model: str | None,
    experts: tuple[str, ...],
    question: str | None,
    timeout_seconds: float,
    as_json: bool,
):
    """Validate no-metered expert consult for another agent."""
    import json
    from typing import cast

    from deepr.mcp.consult_validation import (
        DEFAULT_VALIDATION_QUESTION,
        ValidationBackend,
        run_http_consult_validation,
        run_in_process_consult_validation,
        run_offline_consult_validation,
    )

    backend = cast(ValidationBackend, synthesis_backend.lower())
    if backend == "plan" and not plan:
        raise click.ClickException("--plan is required when --synthesis-backend=plan")

    resolved_question = question or DEFAULT_VALIDATION_QUESTION
    try:
        if url:
            report = run_async_command(
                run_http_consult_validation(
                    url,
                    auth_token=auth_token,
                    question=resolved_question,
                    experts=experts,
                    backend=backend,
                    local_model=local_model,
                    plan=plan,
                    plan_model=plan_model,
                    timeout_seconds=timeout_seconds,
                )
            )
        elif live:
            report = run_async_command(
                run_in_process_consult_validation(
                    question=resolved_question,
                    experts=experts,
                    backend=backend,
                    local_model=local_model,
                    plan=plan,
                    plan_model=plan_model,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            report = run_offline_consult_validation(
                question=resolved_question,
                experts=experts,
                backend=backend,
                plan=plan,
                model=plan_model or local_model,
            )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    payload = report.to_dict()
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        target = report.endpoint or ("in-process" if live else "offline fixture")
        click.echo(f"MCP consult validation: {target}")
        click.echo(f"Backend: {report.backend}")
        for check in report.checks:
            state = "ok" if check.status == "passed" else check.status
            click.echo(f"[{state}] {check.name}: {check.detail}")
        click.echo("Result: passed" if report.ok else "Result: failed")

    if not report.ok:
        sys.exit(1)


@mcp.command("registration-manifest")
@click.argument("url")
@click.option("--agent-name", help="Optional remote agent or host label.")
@click.option("--auth-token", help="Bearer token or scoped-key secret used only for the smoke check.")
@click.option("--timeout", "timeout_seconds", default=10.0, show_default=True, type=click.FloatRange(min=0.1))
@click.option("--skip-smoke", is_flag=True, help="Build the manifest without probing the endpoint.")
@click.option("--output", type=click.Path(dir_okay=False, path_type=str), help="Write the manifest JSON to a file.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON even when --output is provided.")
def registration_manifest(
    url: str,
    agent_name: str | None,
    auth_token: str | None,
    timeout_seconds: float,
    skip_smoke: bool,
    output: str | None,
    as_json: bool,
):
    """Build a token-redacted hosted MCP registration manifest."""
    import json
    from pathlib import Path

    from deepr.mcp.smoke import build_http_registration_manifest, run_http_smoke

    try:
        report = None
        if not skip_smoke:
            report = run_async_command(
                run_http_smoke(
                    url,
                    auth_token=auth_token,
                    timeout_seconds=timeout_seconds,
                )
            )
        payload = build_http_registration_manifest(url, smoke_report=report, agent_name=agent_name)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
        if not as_json:
            click.echo(f"Wrote MCP registration manifest: {output}")
    if as_json or not output:
        click.echo(text, nl=False)

    if report is not None and not report.ok:
        sys.exit(1)


@mcp.command()
def test():
    """Test MCP server with sample requests.

    Sends test requests to verify the server works correctly.
    """
    from deepr.mcp.server import DeeprMCPServer

    async def run_tests():
        server = DeeprMCPServer()

        click.echo("Testing MCP Server...\n")

        # Test 1: List experts
        click.echo("1. Testing list_experts...")
        experts = await server.list_experts()
        click.echo(f"   Found {len(experts)} experts")
        for expert in experts:
            if "error" not in expert:
                click.echo(f"   - {expert['name']}: {expert['domain']}")

        if not experts or "error" in experts[0]:
            click.echo("   No experts found. Create one with: deepr expert make")
            return

        # Test 2: Get expert info
        if experts and "name" in experts[0]:
            expert_name = experts[0]["name"]
            click.echo(f"\n2. Testing get_expert_info for '{expert_name}'...")
            info = await server.get_expert_info(expert_name)
            if "error" not in info:
                click.echo(f"   Documents: {info['stats']['documents']}")
                click.echo(f"   Conversations: {info['stats']['conversations']}")
            else:
                click.echo(f"   Error: {info['error']}")

            # Test 3: Capability map. Keep this diagnostic read-only and $0.
            # Do not call deepr_query_expert here: expert chat can reach a
            # metered model even when the caller intends a no-spend smoke test.
            click.echo("\n3. Testing deepr_capabilities...")
            capabilities = await server.deepr_capabilities()
            if "error" not in capabilities:
                tools = capabilities.get("tools", [])
                click.echo(f"   Schema: {capabilities.get('schema_version', 'unknown')}")
                click.echo(f"   Key tools: {len(tools)}")
                click.echo("   No model calls were run.")
            else:
                click.echo(f"   Error: {capabilities['error']}")

        click.echo("\nOK MCP server tests completed")

    try:
        run_async_command(run_tests())
    except Exception as e:
        click.echo(f"Test failed: {e}", err=True)
        sys.exit(1)
