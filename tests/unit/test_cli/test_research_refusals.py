"""Real research CLI refusals must precede all provider work and reservations."""

import json
import os
from unittest.mock import Mock

import click
import pytest
from click.testing import CliRunner

from deepr.cli.commands import keys, provider_factory, research_safety, run
from deepr.cli.main import cli
from deepr.providers import openrouter_account_controls
from deepr.security.key_quarantine import METERED_KEY_NAMES, QUARANTINE_PREFIX
from deepr.services import openrouter_attended_research as attended

QUERY = "Compare Zig and Rust build systems"
SECRET = "offline-fixture-never-dispatch"


@pytest.fixture(autouse=True)
def offline_research(monkeypatch, tmp_path):
    """Fresh-install state, empty credential roots, and explicit forbidden sinks."""
    monkeypatch.chdir(tmp_path)
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    monkeypatch.setattr(keys, "_user_env_path", lambda: user_dir / ".env")
    monkeypatch.setattr(openrouter_account_controls, "default_data_dir", lambda: user_dir)
    for name in tuple(os.environ):
        if name in METERED_KEY_NAMES or name.startswith(QUARANTINE_PREFIX):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AZURE_PROJECT_ENDPOINT", raising=False)
    for name in (
        "DEEPR_DEEP_RESEARCH_PROVIDER",
        "DEEPR_DEEP_RESEARCH_MODEL",
        "DEEPR_DEFAULT_PROVIDER",
        "DEEPR_DEFAULT_MODEL",
        "DEEPR_VERBOSE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPR_BUDGET_FILE", str(tmp_path / "absent-budget.json"))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "empty-costs"))
    forbidden = Mock(side_effect=AssertionError("provider work or reservation must not run"))
    monkeypatch.setattr(provider_factory, "create_provider_instance", forbidden)
    monkeypatch.setattr(run, "_reserve_job_submission", forbidden)
    monkeypatch.setattr(attended, "open_parent_budget_transaction", forbidden)
    monkeypatch.setattr(attended, "reserve_research_cost", forbidden)
    monkeypatch.setattr(attended, "_dispatch_openrouter_completion", forbidden)
    yield user_dir
    forbidden.assert_not_called()


def assert_refusal(result, flags, code):
    assert result.exit_code == 1, result.output
    assert SECRET not in result.output
    if "--json" in flags:
        payload = json.loads(result.stdout)
        assert result.stderr == ""
        assert payload["schema_version"] == "deepr-cli-operation-result-v1"
        assert payload["kind"] == "deepr.cli.operation_result"
        assert payload["status"] == "error"
        assert payload["error_code"] == code
        assert payload["retryable"] is False
        return payload
    assert result.stderr.strip()


@pytest.mark.parametrize(
    "flags", [[], ["--json"], ["-q"], ["-v"], ["-y"], ["-y", "--json"], ["--json", "--limit", "6"]]
)
def test_missing_credentials_refuse_before_estimate_or_confirmation(monkeypatch, flags):
    from deepr.services import research_bounds

    estimate = Mock(side_effect=AssertionError("cannot estimate execution before checking credentials"))
    confirm = Mock(side_effect=AssertionError("cannot ask to spend without credentials"))
    monkeypatch.setattr(research_bounds, "bounded_research_cost_estimate", estimate)
    monkeypatch.setattr(research_safety, "bounded_research_cost_estimate", estimate)
    monkeypatch.setattr(click, "confirm", confirm)
    result = CliRunner().invoke(cli, ["research", QUERY, *flags])
    assert_refusal(result, flags, "MISSING_API_KEY")
    assert "OPENAI_API_KEY" in result.output
    estimate.assert_not_called()
    confirm.assert_not_called()


def test_azure_missing_credential_has_valid_recovery_guidance():
    result = CliRunner().invoke(cli, ["research", QUERY, "--provider", "azure", "--json"])
    payload = assert_refusal(result, ["--json"], "MISSING_API_KEY")
    assert "AZURE_OPENAI_API_KEY" in payload["error"]
    assert ".env or the environment" in payload["error"]
    assert "keys set azure" not in payload["error"]


def test_azure_foundry_lookup_has_valid_recovery_guidance(capsys):
    from deepr.cli.output import OutputContext, OutputMode

    with pytest.raises(SystemExit) as exc:
        research_safety.require_research_credential("azure-foundry", OutputContext(mode=OutputMode.QUIET))
    assert exc.value.code == 1
    error = capsys.readouterr().err
    assert "AZURE_PROJECT_ENDPOINT" in error
    assert ".env or the environment" in error
    assert "keys set azure-foundry" not in error


def test_high_limit_json_refuses_without_prompt(monkeypatch):
    monkeypatch.setenv(QUARANTINE_PREFIX + "OPENAI_API_KEY", SECRET)
    confirm = Mock(side_effect=AssertionError("JSON must never ask for high-limit confirmation"))
    monkeypatch.setattr(click, "confirm", confirm)
    result = CliRunner().invoke(cli, ["research", QUERY, "--limit", "6", "--json"])
    assert_refusal(result, ["--json"], "INVALID_INPUT")
    confirm.assert_not_called()


@pytest.mark.parametrize("source", ["process", "quarantine", "user-file", "cwd-file"])
def test_stored_credentials_reach_budget_without_becoming_authority(monkeypatch, offline_research, source):
    if source == "process":
        monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    elif source == "quarantine":
        monkeypatch.setenv(QUARANTINE_PREFIX + "OPENAI_API_KEY", SECRET)
    else:
        path = offline_research / ".env" if source == "user-file" else offline_research.parent / ".env"
        path.write_text(f"OPENAI_API_KEY={SECRET}\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["research", QUERY, "--json"])
    payload = assert_refusal(result, ["--json"], "BUDGET_NOT_APPROVED")
    assert payload["category"] == "budget"


@pytest.mark.parametrize("flags", [[], ["--json"], ["-q"], ["-y"], ["--json", "-y"], ["-v"]])
def test_unconfirmed_cost_is_terminal_in_every_output_mode(monkeypatch, flags):
    monkeypatch.setenv(QUARANTINE_PREFIX + "OPENAI_API_KEY", SECRET)
    monkeypatch.setattr(run, "check_budget_approval", lambda _: False)
    result = CliRunner().invoke(cli, ["research", QUERY, *flags], input="n\n")
    assert_refusal(result, flags, "BUDGET_NOT_APPROVED")
    assert "budget" in result.output.lower()


def test_aborted_budget_confirmation_is_terminal(monkeypatch):
    monkeypatch.setenv(QUARANTINE_PREFIX + "OPENAI_API_KEY", SECRET)
    monkeypatch.setattr(run, "check_budget_approval", lambda _: False)
    result = CliRunner().invoke(cli, ["research", QUERY, "-v"], input="")
    assert_refusal(result, ["-v"], "CANCELLED")
    assert "cancelled" in result.stderr.lower()


@pytest.mark.parametrize(
    "query,extra",
    [
        ("", []),
        ("   ", []),
        ("company", []),
        ("x" * 50001, []),
        (QUERY, ["--upload", "missing.pdf"]),
        (QUERY, ["--limit", "0"]),
        (QUERY, ["--limit", "nan"]),
        (QUERY, ["--limit", "inf"]),
    ],
)
@pytest.mark.parametrize("flags", [[], ["--json"], ["-q"]])
def test_invalid_inputs_never_report_success(query, extra, flags):
    result = CliRunner().invoke(cli, ["research", query, *extra, *flags])
    assert_refusal(result, flags, "INVALID_INPUT")


@pytest.mark.parametrize("flags", [[], ["--json"], ["-q"]])
@pytest.mark.parametrize("case", ["empty", "malformed", "unsupported"])
def test_invalid_batch_input_is_a_terminal_refusal(monkeypatch, tmp_path, flags, case):
    from deepr.routing import AutoModeRouter

    batch = tmp_path / ("queries.csv" if case == "unsupported" else "queries.json")
    batch.write_text("not json" if case == "malformed" else '{"queries": []}', encoding="utf-8")
    router = Mock(side_effect=AssertionError("invalid batch must not construct a router"))
    monkeypatch.setattr(AutoModeRouter, "__init__", router)
    result = CliRunner().invoke(cli, ["research", QUERY, "--auto", "--batch", str(batch), *flags])
    assert_refusal(result, flags, "INVALID_INPUT")
    router.assert_not_called()


@pytest.mark.parametrize(
    "provider,model,key", [("openai", "o3-deep-research", "OPENAI_API_KEY"), ("xai", "grok-4.6", "XAI_API_KEY")]
)
def test_preview_and_execution_keep_the_same_environment_route(monkeypatch, provider, model, key):
    from deepr.observability.provider_router import AutonomousProviderRouter
    from deepr.services import research_bounds

    monkeypatch.setenv("DEEPR_DEEP_RESEARCH_PROVIDER", provider)
    monkeypatch.setenv("DEEPR_DEEP_RESEARCH_MODEL", model)
    preview = CliRunner().invoke(cli, ["research", QUERY, "--preview", "--json"])
    assert preview.exit_code == 0
    assert json.loads(preview.stdout)["model"] == model
    monkeypatch.setenv(QUARANTINE_PREFIX + key, SECRET)
    selector = Mock(side_effect=AssertionError("resolved route must never be replaced"))
    monkeypatch.setattr(AutonomousProviderRouter, "select_provider", selector)
    estimate = Mock(wraps=research_bounds.bounded_research_cost_estimate)
    monkeypatch.setattr(research_bounds, "bounded_research_cost_estimate", estimate)
    monkeypatch.setattr(research_safety, "bounded_research_cost_estimate", estimate)
    result = CliRunner().invoke(cli, ["research", QUERY, "--json"])
    assert_refusal(result, ["--json"], "BUDGET_NOT_APPROVED")
    assert len(estimate.call_args_list) >= 2  # Admission and actual _run_single.
    assert all(
        call.kwargs["provider"] == provider and call.kwargs["request"].model == model
        for call in estimate.call_args_list
    )
    selector.assert_not_called()


def test_bounded_admission_failure_is_structured(monkeypatch):
    monkeypatch.setenv(QUARANTINE_PREFIX + "XAI_API_KEY", SECRET)
    result = CliRunner().invoke(cli, ["research", QUERY, "--provider", "xai", "--model", "gemini-3.6-flash", "--json"])
    assert_refusal(result, ["--json"], "research_provider_model_mismatch")


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_preview_is_still_keyless_and_write_free(provider, tmp_path):
    result = CliRunner().invoke(cli, ["research", QUERY, "--provider", provider, "--preview", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["provider"] == provider
    assert payload["executed"] is False
    assert not (tmp_path / "absent-budget.json").exists()


@pytest.mark.parametrize("flags", [[], ["--json"], ["-q"], ["-y"]])
def test_openrouter_without_a_key_never_prompts(monkeypatch, flags):
    confirm = Mock(side_effect=AssertionError("cannot confirm without an OpenRouter key"))
    monkeypatch.setattr(click, "confirm", confirm)
    result = CliRunner().invoke(cli, ["research", QUERY, "--provider", "openrouter", *flags])
    assert_refusal(result, flags, "MISSING_API_KEY")
    confirm.assert_not_called()


@pytest.mark.parametrize("flags", [[], ["--json"], ["-q"], ["-y"], ["--json", "-y"]])
def test_noninteractive_openrouter_refuses_even_with_authority(monkeypatch, flags):
    monkeypatch.setenv(QUARANTINE_PREFIX + "OPENROUTER_API_KEY", SECRET)
    monkeypatch.setattr(attended, "check_budget_approval", lambda _: True)
    confirm = Mock(side_effect=AssertionError("noninteractive modes must not prompt"))
    monkeypatch.setattr(click, "confirm", confirm)
    result = CliRunner().invoke(cli, ["research", QUERY, "--provider", "openrouter", *flags])
    assert_refusal(result, flags, "ATTENDED_EXECUTION_REQUIRED")
    assert "interactive terminal" in result.output
    confirm.assert_not_called()


def test_attended_budget_approval_still_requires_confirmation(monkeypatch):
    monkeypatch.setattr(attended, "check_budget_approval", lambda _: True)
    confirm = Mock(return_value=False)
    monkeypatch.setattr(click, "confirm", confirm)
    with pytest.raises(click.ClickException, match="Cancelled"):
        attended._confirm_openrouter_spend(max_cost=0.01, yes=False)
    confirm.assert_called_once()
