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


@pytest.mark.parametrize("width", [60, 100, 160])
def test_root_help_example_tracks_retained_default(monkeypatch, width):
    from deepr.cli.main import cli
    from deepr.config import ProviderConfig

    monkeypatch.setitem(
        ProviderConfig.model_fields["TASK_MODEL_MAP"].default, "deep_research", ("openai", "gpt-5.6-terra")
    )
    result = CliRunner().invoke(cli, ["--help"], terminal_width=width)
    assert result.exit_code == 0
    assert " \\\n" not in result.output
    if width >= 100:
        assert "--model gpt-5.6-terra --preview" in result.output
    else:
        assert 'deepr research "your question" --preview' in result.output
        assert "Shipped preview baseline: openai / gpt-5.6-terra." in result.output


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


@pytest.mark.parametrize(("module", "command"), [("prep", "plan"), ("docs", "analyze")])
def test_planner_choices_stay_non_empty_after_gpt5_shutdown(module, command):
    """Before #292 these lists held only gpt-5/-mini/-nano, empty after 2026-12-11."""
    cmd = getattr(import_module(f"deepr.cli.commands.{module}"), command)
    option = next(p for p in cmd.params if p.name == "planner")
    after_shutdown = [m for m in option.type.accepted if not is_shutdown(m, today=date(2026, 12, 12))]
    assert {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"} <= set(after_shutdown)
    assert option.default in after_shutdown
    assert option.default.startswith("gpt-5.6-")
    assert "gpt-5" in option.type.accepted


def test_executable_defaults_have_no_retirement_record():
    """Defaults that dispatch on their own must not name a retired or retiring id."""
    import inspect

    from deepr.core.unified_config import UnifiedConfig
    from deepr.experts.constants import UTILITY_MODEL
    from deepr.experts.map_reduce import MapReduceIngester
    from deepr.experts.reflection import DEFAULT_REFLECTION_MODEL
    from deepr.experts.report_absorber import DEFAULT_EXTRACTION_MODEL
    from deepr.observability.provider_router import AutonomousProviderRouter
    from deepr.routing.deprecation import check_deprecation
    from deepr.services.doc_reviewer import DocReviewer
    from deepr.services.expert_validator import ALLOWED_VALIDATION_MODELS, DEFAULT_VALIDATION_MODEL
    from deepr.services.prompt_refiner import PromptRefiner
    from deepr.services.research_planner import ResearchPlanner, create_planner
    from deepr.services.research_reviewer import ResearchReviewer
    from deepr.services.team_architect import TeamArchitect, TeamSynthesizer

    def default(fn, name):
        return inspect.signature(fn).parameters[name].default

    defaults = {
        "UTILITY_MODEL": UTILITY_MODEL,
        "reflection": DEFAULT_REFLECTION_MODEL,
        "extraction": DEFAULT_EXTRACTION_MODEL,
        "validation": DEFAULT_VALIDATION_MODEL,
        "map": default(MapReduceIngester.__init__, "map_model"),
        "planner": default(ResearchPlanner.__init__, "model"),
        "create_planner": default(create_planner, "model"),
        "reviewer": default(ResearchReviewer.__init__, "model"),
        "architect": default(TeamArchitect.__init__, "model"),
        "synthesizer": default(TeamSynthesizer.__init__, "model"),
        "doc_reviewer": default(DocReviewer.__init__, "model"),
        "prompt_refiner": default(PromptRefiner.__init__, "model"),
        "unified_config": UnifiedConfig().default_model,
    }
    for _, model in AutonomousProviderRouter.DEFAULT_FALLBACK_CHAIN:
        defaults[f"fallback:{model}"] = model
    for task, chain in AutonomousProviderRouter.TASK_PREFERENCES.items():
        for _, model in chain:
            defaults[f"{task}:{model}"] = model
    for role, model in defaults.items():
        assert check_deprecation(model) is None, (role, model)
    assert DEFAULT_VALIDATION_MODEL in ALLOWED_VALIDATION_MODELS


@pytest.mark.parametrize(
    ("module", "command", "option_name"),
    [
        ("run", "project", "lead"),
        ("semantic.research", "learn", "lead"),
        ("eval", "eval_calibrate", "grader_model"),
    ],
)
def test_cli_model_defaults_have_no_retirement_record(module, command, option_name):
    from deepr.routing.deprecation import check_deprecation

    mod = import_module(f"deepr.cli.commands.{module}")
    cmd = getattr(mod, command)
    option = next(p for p in cmd.params if p.name == option_name)
    assert option.default == "gpt-5.6-sol"
    assert check_deprecation(option.default) is None


def test_gemini_env_default_is_current(monkeypatch, tmp_path):
    """Only GEMINI_API_KEY set: the env-loaded Gemini default is gemini-3.8-flash, not shut-down 2.0."""
    from pathlib import Path

    from deepr import config as configuration
    from deepr.core.settings import Settings
    from deepr.routing.deprecation import check_deprecation

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(configuration, "_configuration_environment", None)
    monkeypatch.setenv("DEEPR_ENV_FILE", str(tmp_path / "selected.env"))
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "AZURE_OPENAI_KEY", "AZURE_OPENAI_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.chdir(tmp_path)
    Settings.reset()
    try:
        settings = Settings.load(config_path=tmp_path / "absent.yaml", reset_singleton=True)
    finally:
        Settings.reset()

    assert set(settings.providers) >= {"gemini"}
    assert settings.providers["gemini"].default_model == "gemini-3.8-flash"
    assert check_deprecation("gemini-3.8-flash") is None


def test_anthropic_retired_ids_are_refused_not_swapped():
    from deepr.providers.anthropic_provider import ANTHROPIC_PRICING, AnthropicProvider
    from deepr.providers.base import ProviderError

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.model = "claude-opus-5"
    for retired in ("claude-opus-4", "claude-opus-4-1", "claude-sonnet-4"):
        assert retired not in AnthropicProvider.SUPPORTED_MODELS
        assert retired in ANTHROPIC_PRICING
        with pytest.raises(ProviderError, match="retired"):
            provider.get_model_name(retired)
    assert provider.get_model_name("claude-sonnet-4-5") == "claude-sonnet-4-5"
