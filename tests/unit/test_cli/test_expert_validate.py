"""CLI tests for `deepr expert validate`.

The CLI surface is intentionally thin: it loads the expert via ExpertStore,
constructs an ExpertValidator, runs one validation, and renders the result.
These tests stub out the ExpertValidator so the CLI does not need an LLM
and the suite stays hermetic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.main import cli
from deepr.services.expert_validator import ValidationResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _stub_result(verdict: str = "pass") -> ValidationResult:
    return ValidationResult(
        expert_name="Test Expert",
        claim="some claim",
        verdict=verdict,  # type: ignore[arg-type]
        confidence=0.83,
        reasoning="Aligns with the expert's known beliefs.",
        supporting=[],
        contradicting=[],
        caveats=["minor caveat"],
        model="gpt-5-mini",
    )


def _patch_validator(verdict: str = "pass"):
    """Patch ExpertValidator everywhere the CLI looks it up."""
    mock_validator = MagicMock()
    mock_validator.validate = AsyncMock(return_value=_stub_result(verdict))
    return patch(
        "deepr.services.expert_validator.ExpertValidator",
        return_value=mock_validator,
    )


def _patch_store(expert=None):
    if expert is None:
        expert = MagicMock()
    expert.name = "Test Expert"
    return patch(
        "deepr.experts.profile.ExpertStore",
        return_value=MagicMock(load=MagicMock(return_value=expert)),
    )


class TestValidateCommandSurface:
    def test_validate_in_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["expert", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output

    def test_validate_help_describes_intent(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["expert", "validate", "--help"])
        assert result.exit_code == 0
        assert "PASS" in result.output and "WARN" in result.output and "FAIL" in result.output


class TestValidateBehavior:
    def test_pass_verdict_human_output(self, runner: CliRunner) -> None:
        with _patch_store(), _patch_validator("pass"):
            result = runner.invoke(
                cli,
                ["expert", "validate", "Test Expert", "Python uses dynamic typing"],
            )
        assert result.exit_code == 0, result.output
        out = result.output
        assert "PASS" in out
        assert "Test Expert" in out

    def test_fail_verdict_renders_warning(self, runner: CliRunner) -> None:
        with _patch_store(), _patch_validator("fail"):
            result = runner.invoke(
                cli,
                ["expert", "validate", "Test Expert", "Some wrong claim"],
            )
        assert result.exit_code == 0, result.output
        assert "FAIL" in result.output

    def test_warn_verdict_renders_caveats(self, runner: CliRunner) -> None:
        with _patch_store(), _patch_validator("warn"):
            result = runner.invoke(
                cli,
                ["expert", "validate", "Test Expert", "Murky claim"],
            )
        assert result.exit_code == 0, result.output
        assert "WARN" in result.output

    def test_json_output_is_machine_readable(self, runner: CliRunner) -> None:
        with _patch_store(), _patch_validator("pass"):
            result = runner.invoke(
                cli,
                ["expert", "validate", "Test Expert", "ok claim", "--json"],
            )
        assert result.exit_code == 0, result.output
        # Output is pure JSON - no decoration prefix.
        payload = json.loads(result.output)
        assert payload["verdict"] == "pass"
        assert payload["expert_name"] == "Test Expert"
        assert payload["confidence"] == 0.83
        assert payload["model"] == "gpt-5-mini"

    def test_missing_expert_exits_nonzero(self, runner: CliRunner) -> None:
        with patch(
            "deepr.experts.profile.ExpertStore",
            return_value=MagicMock(load=MagicMock(return_value=None)),
        ):
            result = runner.invoke(
                cli,
                ["expert", "validate", "Ghost Expert", "anything"],
            )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_no_claim_exits_nonzero(self, runner: CliRunner) -> None:
        with _patch_store():
            result = runner.invoke(cli, ["expert", "validate", "Test Expert"])
        assert result.exit_code != 0
        assert "claim" in result.output.lower()

    def test_from_file_reads_claim(self, runner: CliRunner, tmp_path: Path) -> None:
        claim_file = tmp_path / "claim.txt"
        claim_file.write_text("Claim sourced from file.")
        with _patch_store(), _patch_validator("pass"):
            result = runner.invoke(
                cli,
                ["expert", "validate", "Test Expert", "--from-file", str(claim_file)],
            )
        assert result.exit_code == 0, result.output
        assert "PASS" in result.output

    def test_from_file_empty_after_strip_errors(self, runner: CliRunner, tmp_path: Path) -> None:
        claim_file = tmp_path / "empty.txt"
        claim_file.write_text("   \n\t  ")
        with _patch_store(), _patch_validator("pass"):
            result = runner.invoke(
                cli,
                ["expert", "validate", "Test Expert", "--from-file", str(claim_file)],
            )
        assert result.exit_code != 0
        assert "empty" in result.output.lower()
