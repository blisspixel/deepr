"""MCP (Model Context Protocol) server commands."""

import sys

import click

from deepr.cli.async_runner import run_async_command


@click.group()
def mcp():
    """Model Context Protocol server for AI agent integration."""
    pass


@mcp.group()
def keys():
    """Manage experimental scoped API keys for HTTP MCP access."""
    pass


def _load_key_store(keys_path: str | None):
    from pathlib import Path

    from deepr.mcp.security.scoped_keys import ScopedMCPKeyStore

    return ScopedMCPKeyStore(Path(keys_path)) if keys_path else ScopedMCPKeyStore()


def _key_record_payload(record, *, include_secret: str | None = None):
    payload = record.to_dict(include_secret_hash=False)
    if include_secret is not None:
        payload["secret"] = include_secret
    return payload


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
@click.option("--keys-path", type=click.Path(dir_okay=False, path_type=str), help="Override key-store path.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def create_key(
    key_id: str | None, mode: str, experts: tuple[str, ...], budget: float | None, keys_path: str | None, as_json: bool
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
        click.echo(
            f"{record.key_id}\t{status}\tmode={record.mode.value}\texperts={experts}\tbudget={budget}\tlast_used={last_used}"
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


@mcp.command()
def serve():
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

            # Test 3: Query expert
            click.echo("\n3. Testing query_expert...")
            result = await server.query_expert(expert_name, "What is your domain expertise?", budget=0.0, agentic=False)
            if "error" not in result:
                click.echo(f"   Answer: {result['answer'][:200]}...")
                click.echo(f"   Cost: ${result['cost']:.4f}")
            else:
                click.echo(f"   Error: {result['error']}")

        click.echo("\n✓ MCP server tests completed")

    try:
        run_async_command(run_tests())
    except Exception as e:
        click.echo(f"Test failed: {e}", err=True)
        sys.exit(1)
