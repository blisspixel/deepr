"""Config commands - validate and manage configuration."""

import click
from deepr.branding import print_section_header, CHECK, CROSS


@click.group()
def config():
    """Manage and validate configuration."""
    pass


@config.command()
def validate():
    """
    Validate configuration and check API connectivity.

    Checks:
    - API keys are set
    - Required directories exist
    - API connectivity
    - Configuration validity

    Example:
        deepr config validate
    """
    print_section_header("Configuration Validation")

    try:
        import os
        import asyncio
        from pathlib import Path
        from deepr.config import load_config

        errors = []
        warnings = []

        click.echo("\nChecking configuration...\n")

        # Load config
        try:
            config = load_config()
            click.echo(f"{CHECK} Configuration file loaded")
        except Exception as e:
            click.echo(f"{CROSS} Failed to load configuration: {e}", err=True)
            raise click.Abort()

        # Check API key
        api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            errors.append("OPENAI_API_KEY not set")
            click.echo(f"{CROSS} OpenAI API key not found")
        elif api_key.startswith("sk-"):
            click.echo(f"{CHECK} OpenAI API key found")
        else:
            warnings.append("API key format looks unusual")
            click.echo(f"   Warning: API key format looks unusual")

        # Check directories
        queue_db_path = config.get("queue_db_path", "queue/research_queue.db")
        queue_dir = Path(queue_db_path).parent
        if not queue_dir.exists():
            warnings.append(f"Queue directory does not exist: {queue_dir}")
            click.echo(f"   Warning: Queue directory will be created: {queue_dir}")
        else:
            click.echo(f"{CHECK} Queue directory exists: {queue_dir}")

        results_dir = config.get("results_dir", "data/reports")
        if not Path(results_dir).exists():
            warnings.append(f"Results directory does not exist: {results_dir}")
            click.echo(f"   Warning: Results directory will be created: {results_dir}")
        else:
            click.echo(f"{CHECK} Results directory exists: {results_dir}")

        # Check budget limits
        max_per_job = config.get("max_cost_per_job")
        max_per_day = config.get("max_cost_per_day")
        max_per_month = config.get("max_cost_per_month")

        if max_per_job:
            click.echo(f"{CHECK} Budget limit per job: ${max_per_job:.2f}")
        else:
            warnings.append("No per-job budget limit set")
            click.echo(f"   Warning: No per-job budget limit set")

        # Test API connectivity
        if api_key:
            click.echo(f"\nTesting API connectivity...")
            try:
                from deepr.providers import create_provider
                provider = create_provider(
                    config.get("provider", "openai"),
                    api_key=api_key
                )

                # Simple API test - just check we can create the client
                click.echo(f"{CHECK} Provider initialized successfully")

                # Try to list vector stores to verify connectivity
                async def test_api():
                    try:
                        stores = await provider.list_vector_stores(limit=1)
                        return True
                    except Exception as e:
                        return str(e)

                result = asyncio.run(test_api())
                if result is True:
                    click.echo(f"{CHECK} API connectivity verified")
                else:
                    errors.append(f"API connection failed: {result}")
                    click.echo(f"{CROSS} API connection failed: {result}")

            except Exception as e:
                errors.append(f"Provider initialization failed: {e}")
                click.echo(f"{CROSS} Provider initialization failed: {e}")

        # Summary
        click.echo(f"\n{'='*60}")
        if errors:
            click.echo(f"\n{CROSS} Validation failed with {len(errors)} error(s):\n")
            for error in errors:
                click.echo(f"   {CROSS} {error}")
        else:
            click.echo(f"\n{CHECK} Configuration is valid!")

        if warnings:
            click.echo(f"\nWarnings ({len(warnings)}):")
            for warning in warnings:
                click.echo(f"   - {warning}")

        if errors:
            raise click.Abort()

    except Exception as e:
        if not isinstance(e, click.Abort):
            click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@config.command()
def show():
    """
    Display current configuration (sanitized).

    Shows configuration with sensitive values masked.

    Example:
        deepr config show
    """
    print_section_header("Current Configuration")

    try:
        import os
        from deepr.config import load_config

        config = load_config()

        click.echo("\nProvider:")
        click.echo(f"   Type: {config.get('provider', 'openai')}")

        api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        if api_key:
            masked = api_key[:7] + "..." + api_key[-4:] if len(api_key) > 11 else "***"
            click.echo(f"   API Key: {masked}")

        click.echo("\nStorage:")
        click.echo(f"   Queue DB: {config.get('queue_db_path', 'queue/research_queue.db')}")
        click.echo(f"   Results: {config.get('results_dir', 'data/reports')}")

        click.echo("\nBudget Limits:")
        click.echo(f"   Per Job: ${config.get('max_cost_per_job', 10.0):.2f}")
        click.echo(f"   Per Day: ${config.get('max_cost_per_day', 100.0):.2f}")
        click.echo(f"   Per Month: ${config.get('max_cost_per_month', 1000.0):.2f}")

        click.echo("\nDefaults:")
        click.echo(f"   Model: {config.get('default_model', 'o4-mini-deep-research')}")
        click.echo(f"   Auto-refine: {os.getenv('DEEPR_AUTO_REFINE', 'false')}")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@config.command()
@click.argument("key")
@click.argument("value")
def set(key: str, value: str):
    """
    Set a configuration value in .env file.

    Example:
        deepr config set DEEPR_AUTO_REFINE true
        deepr config set DEEPR_MAX_COST_PER_JOB 5.0
    """
    print_section_header(f"Set Configuration: {key}")

    try:
        from pathlib import Path

        env_file = Path(".env")

        if not env_file.exists():
            click.echo(f"{CROSS} .env file not found. Copy .env.example first.", err=True)
            raise click.Abort()

        # Read current content
        lines = env_file.read_text().splitlines()

        # Find and update or append
        found = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"{key}={value}")

        # Write back
        env_file.write_text("\n".join(new_lines) + "\n")

        click.echo(f"\n{CHECK} Configuration updated: {key}={value}")
        click.echo(f"\nRestart any running services for changes to take effect")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()
