"""Config commands - validate and manage configuration."""

import click

from deepr.cli.async_runner import run_async_command
from deepr.cli.colors import console, print_error, print_section_header, print_success

_CLI_ENV_KEY_ALIASES = {
    "cli.branding": "DEEPR_BRANDING",
    "cli.animations": "DEEPR_ANIMATIONS",
}

_ALLOWED_CONFIG_VALUES = {
    "DEEPR_BRANDING": {"off", "on", "auto"},
    "DEEPR_ANIMATIONS": {"off", "light", "full"},
}


@click.group()
def config():
    """Manage and validate configuration."""
    pass


def _get_settings():
    """Get consolidated Settings instance."""
    from deepr.core.settings import get_settings

    return get_settings()


def _get_unified_config():
    """Get UnifiedConfig, falling back to AppConfig if needed.

    Deprecated: Use _get_settings() for new code.
    """
    try:
        from deepr.core.unified_config import UnifiedConfig

        return UnifiedConfig.load()
    except Exception:
        # Fallback to AppConfig bridge
        from deepr.config import AppConfig
        from deepr.core.unified_config import UnifiedConfig

        app_config = AppConfig.from_env()
        return UnifiedConfig.from_app_config(app_config)


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
        from pathlib import Path

        # Use consolidated Settings
        settings = _get_settings()

        errors = []
        warnings = []

        console.print("\nChecking configuration...\n")
        console.print(f"[dim]Config source: {settings._source}[/dim]\n")

        # Validate using Settings
        validation_errors = settings.validate()
        for err in validation_errors:
            errors.append(err)
            console.print(f"[error]{err}[/error]")

        # Check API key for default provider
        api_key = settings.get_api_key(settings.default_provider)
        if not api_key:
            # Try OpenAI as fallback
            api_key = settings.get_api_key("openai") or os.getenv("OPENAI_API_KEY")

        if not api_key:
            if "No API key for default provider" not in str(errors):
                errors.append(f"No API key for provider '{settings.default_provider}'")
            console.print(f"[error]API key not found for {settings.default_provider}[/error]")
        else:
            console.print(f"[success]API key found for {settings.default_provider}[/success]")

        # Check directories
        data_dir = Path(settings.data_dir)
        if not data_dir.exists():
            warnings.append(f"Data directory does not exist: {data_dir}")
            console.print(f"   Warning: Data directory will be created: {data_dir}")
        else:
            console.print(f"[success]Data directory exists: {data_dir}[/success]")

        queue_db_path = "queue/research_queue.db"
        queue_dir = Path(queue_db_path).parent
        if not queue_dir.exists():
            warnings.append(f"Queue directory does not exist: {queue_dir}")
            console.print(f"   Warning: Queue directory will be created: {queue_dir}")
        else:
            console.print(f"[success]Queue directory exists: {queue_dir}[/success]")

        results_dir = settings.storage.local_path
        if not Path(results_dir).exists():
            warnings.append(f"Results directory does not exist: {results_dir}")
            console.print(f"   Warning: Results directory will be created: {results_dir}")
        else:
            console.print(f"[success]Results directory exists: {results_dir}[/success]")

        # Check budget limits
        if settings.budget.daily_limit > 0:
            console.print(f"[success]Daily budget limit: ${settings.budget.daily_limit:.2f}[/success]")
        else:
            warnings.append("No daily budget limit set")
            console.print("   Warning: No daily budget limit set")

        if settings.budget.monthly_limit > 0:
            console.print(f"[success]Monthly budget limit: ${settings.budget.monthly_limit:.2f}[/success]")

        # Test API connectivity
        if api_key:
            console.print("\nTesting API connectivity...")
            try:
                from deepr.providers import create_provider

                provider = create_provider(settings.default_provider, api_key=api_key)

                # Simple API test - just check we can create the client
                console.print("[success]Provider initialized successfully[/success]")

                # Try to list vector stores to verify connectivity
                async def test_api():
                    try:
                        await provider.list_vector_stores(limit=1)
                        return True
                    except Exception as e:
                        return str(e)

                result = run_async_command(test_api())
                if result is True:
                    console.print("[success]API connectivity verified[/success]")
                else:
                    errors.append(f"API connection failed: {result}")
                    console.print(f"[error]API connection failed: {result}[/error]")

            except Exception as e:
                errors.append(f"Provider initialization failed: {e}")
                console.print(f"[error]Provider initialization failed: {e}[/error]")

        # Summary
        console.print(f"\n{'=' * 60}")
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
@click.option("--unified", is_flag=True, help="Show UnifiedConfig format (deprecated)")
@click.option("--legacy", is_flag=True, help="Show legacy config format")
def show(unified: bool, legacy: bool):
    """
    Display current configuration (sanitized).

    Shows configuration with sensitive values masked.

    Example:
        deepr config show
        deepr config show --legacy
    """
    print_section_header("Current Configuration")

    try:
        import os

        if legacy:
            # Legacy format for backward compatibility
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

            console.print("\n[dim]Tip: Remove --legacy flag to see new config format[/dim]")
        else:
            # New consolidated Settings format (default)
            settings = _get_settings()
            console.print(settings.show(mask_keys=True))

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

        normalized_key, normalized_value = _normalize_config_key_value(key, value)
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
            if line.startswith(f"{normalized_key}="):
                new_lines.append(f"{normalized_key}={normalized_value}")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"{normalized_key}={normalized_value}")

        # Write back
        env_file.write_text("\n".join(new_lines) + "\n")

        print_success(f"Configuration updated: {normalized_key}={normalized_value}")
        console.print("\nRestart any running services for changes to take effect")

    except click.ClickException as e:
        print_error(str(e))
        raise click.Abort()
    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


def _normalize_config_key_value(key: str, value: str) -> tuple[str, str]:
    """Normalize config aliases and validate constrained values."""
    normalized_key = key.strip()
    alias = normalized_key.lower()

    if alias.startswith("cli.") and alias not in _CLI_ENV_KEY_ALIASES:
        valid_keys = ", ".join(sorted(_CLI_ENV_KEY_ALIASES))
        raise click.ClickException(f"Unknown CLI config key '{key}'. Valid keys: {valid_keys}")

    normalized_key = _CLI_ENV_KEY_ALIASES.get(alias, normalized_key)
    normalized_value = value.strip()

    allowed_values = _ALLOWED_CONFIG_VALUES.get(normalized_key)
    if allowed_values is not None:
        normalized_value = normalized_value.lower()
        if normalized_value not in allowed_values:
            allowed_list = ", ".join(sorted(allowed_values))
            raise click.ClickException(
                f"Invalid value '{value}' for {normalized_key}. Allowed values: {allowed_list}"
            )

    return normalized_key, normalized_value
