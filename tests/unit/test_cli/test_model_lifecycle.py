"""Offline regressions for model notices, choices and first-run guidance."""

from datetime import date
from importlib import import_module
from io import StringIO

import click
import pytest
from click.testing import CliRunner
from rich.console import Console

from deepr.cli.model_choices import ModelChoice, is_shutdown, model_note, research_model_choice


@pytest.mark.parametrize(
    "module,command",
    [
        ("research", "submit"),
        ("cost", "estimate"),
        ("costs", "estimate"),
        ("docs", "analyze"),
        ("prep", "plan"),
        ("team", "analyze"),
    ],
)
def test_research_choices_hide_shutdown_ids_but_keep_explicit_notice(module, command):
    cmd = getattr(import_module(f"deepr.cli.commands.{module}"), command)
    option = next(p for p in cmd.params if p.name == "model")
    assert isinstance(option.type, click.Choice)
    assert all(not is_shutdown(model) for model in option.type.choices)
    assert "gpt-5.6-sol" in option.type.choices
    for retired in ("o3-deep-research", "o4-mini-deep-research"):

        @click.command()
        @click.option("--model", type=option.type)
        def probe(model):
            click.echo(model)

        result = CliRunner().invoke(probe, ["--model", retired])
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == retired
        assert "2026-07-23" in result.stderr
        assert "gpt-5.6-sol" in result.stderr


def test_choice_rejects_unknown_names_and_does_not_advertise_retired_completions():
    choice = research_model_choice()
    with pytest.raises(click.BadParameter):
        choice.convert("o3-deep-research-made-up", None, None)
    ctx = click.Context(click.Command("probe"))
    assert not choice.shell_complete(ctx, click.Option(["--model"]), "o3")


def test_shutdown_boundary_and_family_notice_are_exact():
    assert not is_shutdown("gpt-5-mini", today=date(2026, 12, 10))
    assert is_shutdown("gpt-5-mini", today=date(2026, 12, 11))
    assert model_note("gpt-5-mini-2025-08-07")
    assert not model_note("gpt-5-pro")
    assert not model_note("gpt-5.6-sol")
    assert not model_note("gpt-5-made-up")
    assert ModelChoice(["gpt-5.6-sol"]).convert("gpt-5.6-sol", None, None) == "gpt-5.6-sol"


def test_generated_help_uses_owning_defaults_and_candidate_registry(monkeypatch):
    from deepr.cli.commands.help import providers
    from deepr.config import ProviderConfig
    from deepr.providers.registry import MODEL_CAPABILITIES
    from deepr.providers.reviewed_catalog import REVIEWED_CAPABILITIES

    monkeypatch.setitem(ProviderConfig.model_fields["TASK_MODEL_MAP"].default, "planning", ("openai", "gpt-5.6-terra"))
    result = CliRunner().invoke(providers, terminal_width=160)
    assert result.exit_code == 0, result.output
    assert "gpt-5.6-terra" in result.output
    assert "o3-deep-research" not in result.output
    for key in REVIEWED_CAPABILITIES:
        cap = MODEL_CAPABILITIES[key]
        if not is_shutdown(cap.model):
            assert cap.model in result.output
    assert "Preview only" in result.output


@pytest.mark.parametrize(
    "vram,expected,offers_pull",
    [
        (40_000_000_000, "fits", True),
        (8_000_000_000, "Choose a smaller model", False),
        (0, "GPU capacity unknown", False),
    ],
)
def test_local_setup_does_not_assume_fit(monkeypatch, vram, expected, offers_pull):
    module = import_module("deepr.cli.commands.init")
    monkeypatch.setattr("deepr.backends.local_fit.detect_vram_bytes", lambda: vram)
    output = StringIO()
    monkeypatch.setattr(module, "console", Console(file=output, width=160, color_system=None))
    module._print_local_setup()
    rendered = output.getvalue()
    assert "18 GB download" in rendered
    assert "cloud disabled persistently" in rendered
    assert expected in rendered
    assert ("ollama pull" in rendered) is offers_pull


def test_root_help_example_tracks_retained_default(monkeypatch):
    from deepr.cli.main import cli
    from deepr.config import ProviderConfig

    monkeypatch.setitem(
        ProviderConfig.model_fields["TASK_MODEL_MAP"].default, "deep_research", ("openai", "gpt-5.6-terra")
    )
    result = CliRunner().invoke(cli, ["--help"], terminal_width=160)
    assert result.exit_code == 0
    assert "--model gpt-5.6-terra --preview" in result.output


def test_web_allowlist_excludes_shutdown_models():
    from deepr.web.app import _WEB_OPENAI_RESEARCH_MODELS

    assert all(not is_shutdown(model) for model in _WEB_OPENAI_RESEARCH_MODELS)


async def test_doctor_reports_access_without_claiming_shutdown(monkeypatch):
    from types import SimpleNamespace

    from deepr.cli.commands.doctor import check_deprecated_models
    from deepr.config import AppConfig

    config = SimpleNamespace(
        provider=SimpleNamespace(
            default_provider="gemini",
            default_model="gemini-2.5-flash",
            deep_research_provider="openai",
            deep_research_model="gpt-5.6-sol",
        )
    )
    monkeypatch.setattr(AppConfig, "from_env", lambda: config)
    monkeypatch.setattr("deepr.cli.commands.provider_factory.credential_presence", lambda provider: (True, "fixture"))
    checks = await check_deprecated_models({})
    assert len(checks) == 1
    assert checks[0].category == "Model Access"
    assert "eligibility unverified" in checks[0].message
    assert "no announced shutdown" in checks[0].details[0]


def test_explicit_restricted_preview_keeps_json_stdout_and_access_notice():
    import json
    from deepr.cli.main import cli

    result = CliRunner().invoke(
        cli, ["research", "test", "--provider", "gemini", "--model", "gemini-2.5-flash", "--preview", "--json"]
    )
    payload = json.loads(result.stdout)
    assert "prior users only" in result.stderr
    assert "https://ai.google.dev/gemini-api/docs/deprecations" in result.stderr
    assert result.exit_code == 0
    assert payload["executed"] is False
    assert payload["model"] == "gemini-2.5-flash"
    assert payload["model_access"]["state"] == "legacy_access_only"
    assert payload["model_access"]["account_verified"] is False
    assert "prior users only" in payload["model_access"]["note"]
