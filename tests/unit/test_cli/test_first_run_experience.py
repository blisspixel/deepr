"""Offline first-run contracts through the actual CLI and settings seams."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.core.settings import Settings


@pytest.fixture(autouse=True)
def settings_reset(monkeypatch, tmp_path):
    from deepr import config as configuration

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(configuration, "_configuration_environment", None)
    monkeypatch.setenv("DEEPR_ENV_FILE", str(tmp_path / "selected.env"))
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    Settings.reset()
    yield
    Settings.reset()


def test_budget_display_preserves_request_before_fail_closed_clamp(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPR_BUDGET_FILE", str(tmp_path / "missing-budget.json"))
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "1")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "2")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "5")
    settings = Settings.load()
    output = settings.show()
    assert "Per Job: $0.00 effective ($1.00 requested)" in output
    assert "Daily: $0.00 effective ($2.00 requested)" in output
    assert "Monthly: $0.00 effective ($5.00 requested)" in output
    assert "account controls are not configured" in output
    assert "Numeric ceilings do not authorize a provider" in output
    assert settings.budget.monthly_limit == 0


def test_budget_set_document_is_not_provider_authorization(monkeypatch, tmp_path):
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps({"monthly_limit": 5, "monthly_spending": 0}))
    monkeypatch.setenv("DEEPR_BUDGET_FILE", str(budget))
    output = Settings.load().show()
    assert "$0.00 effective" in output
    assert "authorization is missing or unverified" in output
    assert "budget authorize openrouter" in output


def test_config_show_names_canonical_research_route_and_compatibility_defaults(monkeypatch):
    monkeypatch.setenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
    monkeypatch.setenv("DEEPR_DEEP_RESEARCH_MODEL", "o3-deep-research")
    result = CliRunner().invoke(cli, ["config", "show"])
    assert result.exit_code == 0, result.output
    assert "Research workflow default: openai / o3-deep-research" in result.output
    assert "Compatibility Provider Settings" in result.output
    assert "explicit attended OpenRouter" in result.output


def test_root_help_describes_attended_exception_and_lazy_command():
    output = CliRunner().invoke(cli, ["--help"]).output
    assert "Explicit attended OpenRouter" in output
    assert "budget authorize openrouter" in output
    assert "Preview research or run explicit attended OpenRouter" in output
    assert "Metered research is preview-only in the current release" not in output


def test_init_help_preserves_example_lines():
    output = CliRunner().invoke(cli, ["init", "--help"]).output
    lines = output.splitlines()
    assert any(line.strip().startswith("deepr init --yes") for line in lines)
    assert any(line.strip().startswith("deepr init --budget 3") for line in lines)


@pytest.mark.asyncio
async def test_doctor_detects_quarantined_openrouter_without_releasing_or_printing_key(monkeypatch):
    from deepr.cli.commands.doctor import check_api_keys, check_provider_connectivity
    from deepr.security.key_quarantine import QUARANTINE_PREFIX

    secret = "stored-openrouter-secret-for-offline-test"
    monkeypatch.setenv(QUARANTINE_PREFIX + "OPENROUTER_API_KEY", secret)
    checks = await check_api_keys({}) + await check_provider_connectivity({})
    by_name = {check.name: check for check in checks}
    assert by_name["OpenRouter API Key"].passed
    assert not by_name["OpenRouter API Connectivity"].passed
    rendered = " ".join(check.message + " " + " ".join(check.details) for check in checks)
    assert secret not in rendered
    import os

    assert "OPENROUTER_API_KEY" not in os.environ


@pytest.mark.asyncio
async def test_doctor_unconfigured_provider_defaults_do_not_warn(monkeypatch):
    from deepr.cli.commands import doctor

    monkeypatch.setattr("deepr.cli.commands.provider_factory.credential_presence", lambda _: (False, "UNSET"))
    assert await doctor.check_deprecated_models({}) == []


@pytest.mark.asyncio
async def test_doctor_summary_separates_required_optional_and_unverified(capsys):
    from deepr.cli.commands.doctor import DiagnosticCheck, check_local_ollama, print_checks

    core = DiagnosticCheck("Required filesystem", "Filesystem")
    core.passed = True
    optional = DiagnosticCheck("Unset optional", "Optional")
    optional.failure_severity = "info"
    checks = [core, optional, *(await check_local_ollama(skip_connectivity=True))]
    print_checks(checks)
    output = capsys.readouterr().out
    assert "1/1 required checks passed" in output
    assert "1 optional" in output and "1 unverified" in output
    assert "All good" not in output
