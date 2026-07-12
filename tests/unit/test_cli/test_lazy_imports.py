"""Cold-start import posture and lazy top-level command discovery."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import click

from deepr.cli.main import cli

_TOP_LEVEL_COMMANDS = {
    "a2a",
    "agentic",
    "analytics",
    "budget",
    "cancel",
    "capacity",
    "check",
    "completion",
    "config",
    "cost",
    "costs",
    "diagnostics",
    "docs",
    "doctor",
    "eval",
    "expert",
    "fleet",
    "get",
    "help",
    "init",
    "interactive",
    "jobs",
    "knowledge",
    "l",
    "learn",
    "list",
    "make",
    "mcp",
    "migrate",
    "providers",
    "r",
    "research",
    "route",
    "run",
    "s",
    "search",
    "skill",
    "status",
    "team",
    "templates",
    "upgrade",
    "vector",
    "web",
}


def _run_clean_interpreter(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def test_version_and_root_help_do_not_import_heavy_runtime_modules() -> None:
    result = _run_clean_interpreter(
        """
        import sys
        from click.testing import CliRunner
        from deepr.cli.main import cli

        runner = CliRunner()
        for args in (["--version"], ["--help"]):
            outcome = runner.invoke(cli, args)
            assert outcome.exit_code == 0, outcome.output

        blocked_prefixes = (
            "anthropic",
            "azure",
            "google",
            "numpy",
            "openai",
            "deepr.experts.chat",
            "deepr.providers.anthropic_provider",
            "deepr.providers.azure_foundry_provider",
            "deepr.providers.azure_provider",
            "deepr.providers.gemini_provider",
            "deepr.providers.openai_provider",
        )
        blocked = sorted(
            name
            for name in sys.modules
            if any(name == prefix or name.startswith(prefix + ".") for prefix in blocked_prefixes)
        )
        assert blocked == [], blocked
        """
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_command_registry_discovers_every_public_and_compatibility_name() -> None:
    context = click.Context(cli)

    assert cli.list_commands(context) == sorted(_TOP_LEVEL_COMMANDS)
    for name in _TOP_LEVEL_COMMANDS:
        assert isinstance(cli.get_command(context, name), click.Command), name
    assert cli.get_command(context, "not-a-deepr-command") is None


def test_compatibility_aliases_stay_hidden_after_lazy_resolution() -> None:
    context = click.Context(cli)

    for name in {"cancel", "cost", "get", "l", "list", "r", "s", "status"}:
        command = cli.get_command(context, name)
        assert command is not None
        assert command.hidden is True


def test_provider_package_loads_each_sdk_only_when_selected() -> None:
    result = _run_clean_interpreter(
        """
        import sys
        import deepr.providers as providers

        assert "openai" not in sys.modules
        assert "anthropic" not in sys.modules
        assert "google.genai" not in sys.modules
        assert "azure" not in sys.modules

        assert providers.OpenAIProvider.__name__ == "OpenAIProvider"
        assert "openai" in sys.modules
        assert "anthropic" not in sys.modules
        assert "google.genai" not in sys.modules
        assert "azure" not in sys.modules
        """
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_expert_package_defers_chat_and_numpy_until_their_exports_are_used() -> None:
    result = _run_clean_interpreter(
        """
        import sys
        import deepr.experts as experts

        assert "numpy" not in sys.modules
        assert "deepr.experts.chat" not in sys.modules

        assert experts.ExpertProfile.__name__ == "ExpertProfile"
        assert "numpy" not in sys.modules
        assert "deepr.experts.chat" not in sys.modules

        assert experts.EmbeddingCache.__name__ == "EmbeddingCache"
        assert "numpy" in sys.modules
        assert "deepr.experts.chat" not in sys.modules
        """
    )

    assert result.returncode == 0, result.stdout + result.stderr
