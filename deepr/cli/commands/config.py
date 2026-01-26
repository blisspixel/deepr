"""Config commands - validate and manage configuration."""

import click
from deepr.cli.colors import print_section_header, print_success, print_error, print_warning, console


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

        console.print("\nChecking configuration...\n")

        # Load config
        try:
            config = load_config()
            console.print("[success]Configuration file loaded[/success]")
        except Exception as e:
            print_error(f"Failed to load configuration: {e}")
            raise click.Abort()

        # Check API key
        api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            errors.append("OPENAI_API_KEY not set")
            console.print("[error]OpenAI API key not found[/error]")
        elif api_key.startswith("sk-"):
            console.print("[success]OpenAI API key found[/success]")
        else:
            warnings.append("API key format looks unusual")
            console.print("   Warning: API key format looks unusual")

        # Check directories
        queue_db_path = config.get("queue_db_path", "queue/research_queue.db")
        queue_dir = Path(queue_db_path).parent
        if not queue_dir.exists():
            warnings.append(f"Queue directory does not exist: {queue_dir}")
            console.print(f"   Warning: Queue directory will be created: {queue_dir}")
        else:
            console.print(f"[success]Queue directory exists: {queue_dir}[/success]")

        results_dir = config.get("results_dir", "data/reports")
        if not Path(results_dir).exists():
            warnings.append(f"Results directory does not exist: {results_dir}")
            console.print(f"   Warning: Results directory will be created: {results_dir}")
        else:
            console.print(f"[success]Results directory exists: {results_dir}[/success]")

        # Check budget limits
        max_per_job = config.get("max_cost_per_job")
        max_per_day = config.get("max_cost_per_day")
        max_per_month = config.get("max_cost_per_month")

        if max_per_job:
            console.print(f"[success]Budget limit per job: ${max_per_job:.2f}[/success]")
        else:
            warnings.append("No per-job budget limit set")
            console.print(f"   Warning: No per-job budget limit set")

        # Test API connectivity
        if api_key:
            console.print(f"\nTesting API connectivity...")
            try:
                from deepr.providers import create_provider
                provider = create_provider(
                    config.get("provider", "openai"),
                    api_key=api_key
                )

                # Simple API test - just check we can create the client
                console.print("[success]Provider initialized successfully[/success]")

                # Try to list vector stores to verify connectivity
                async def test_api():
                    try:
                        stores = await provider.list_vector_stores(limit=1)
                        return True
                    except Exception as e:
                        return str(e)

                result = asyncio.run(test_api())
                if result is True:
                    console.print("[success]API connectivity verified[/success]")
                else:
                    errors.append(f"API connection failed: {result}")
                    console.print(f"[error]API connection failed: {result}[/error]")

            except Exception as e:
                errors.append(f"Provider initialization failed: {e}")
                console.print(f"[error]Provider initialization failed: {e}[/error]")

        # Summary
        console.print(f"\n{'='*60}")
        if errors:
            print_error(f"Validation failed with {len(errors)} error(s):")
            for error in errors:
                console.print(f"   [error]{error}[/error]")
        else:
            print_success("Configuration is valid!")

        if warnings:
            console.print(f"\nWarnings ({len(warnings)}):")
            for warning in warnings:
                console.print(f"   - {warning}")

        if errors:
            raise click.Abort()

    except Exception as e:
        if not isinstance(e, click.Abort):
            print_error(f"Error: {e}")
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
        click.echo(f"   Per Job: ${config.get('max_cost_per_job', 5.0):.2f}")
        click.echo(f"   Per Day: ${config.get('max_daily_cost', 25.0):.2f}")
        click.echo(f"   Per Month: ${config.get('max_monthly_cost', 200.0):.2f}")

        console.print("\nDefaults:")
        console.print(f"   Model: {config.get('default_model', 'o4-mini-deep-research')}")
        console.print(f"   Auto-refine: {os.getenv('DEEPR_AUTO_REFINE', 'false')}")

    except Exception as e:
        print_error(f"Error: {e}")
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
            print_error(".env file not found. Copy .env.example first.")
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

        print_success(f"Configuration updated: {key}={value}")
        console.print(f"\nRestart any running services for changes to take effect")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()
