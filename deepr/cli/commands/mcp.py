"""MCP (Model Context Protocol) server commands."""

import sys

import click


@click.group()
def mcp():
    """Model Context Protocol server for AI agent integration."""
    pass


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
    import asyncio

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
        asyncio.run(run_tests())
    except Exception as e:
        click.echo(f"Test failed: {e}", err=True)
        sys.exit(1)
