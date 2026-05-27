"""Unit tests for ``deepr research --preview`` (routing preview).

Verifies that preview / dry-run mode shows the planned model + provider +
estimated cost band without making any provider call or submitting a job.

Covers:
- ``--preview`` (and the back-compat ``--dry-run`` alias) for explicit
  --model/--provider runs.
- ``--auto --preview`` for routed runs.
- JSON output structure for both code paths.
- Confirmation that no provider client and no job submission occur.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestPreviewFlagShape:
    """Help text + flag accessibility."""

    def test_preview_flag_shown_in_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["research", "--help"])
        assert result.exit_code == 0
        assert "--preview" in result.output

    def test_dry_run_still_in_help_as_alias(self, runner: CliRunner) -> None:
        """--dry-run remains as a back-compat alias on the same flag."""
        result = runner.invoke(cli, ["research", "--help"])
        assert result.exit_code == 0
        # Help renders the canonical name (--preview) but the alias still
        # works on the command line; verified separately below.
        assert "preview" in result.output.lower()


class TestPreviewExplicitModel:
    """``--preview`` on an explicit --model/--provider run."""

    def test_preview_shows_provider_and_model(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "research",
                "--preview",
                "-m",
                "o3-deep-research",
                "-p",
                "openai",
                "What is quantum entanglement?",
            ],
        )
        assert result.exit_code == 0, result.output
        out = result.output
        assert "o3-deep-research" in out
        assert "openai" in out
        assert "Est. cost" in out
        assert "preview only" in out.lower()

    def test_preview_no_provider_call_made(self, runner: CliRunner) -> None:
        """Preview must not submit a research job.

        _run_single is the single funnel through which the explicit-model
        path reaches the provider; if it's never called, no provider
        client is constructed and no money is spent.
        """
        import sys

        research_mod = sys.modules["deepr.cli.commands.semantic.research"]
        with patch.object(research_mod, "_run_single") as mock_single:
            result = runner.invoke(
                cli,
                [
                    "research",
                    "--preview",
                    "-m",
                    "o3-deep-research",
                    "What is quantum entanglement?",
                ],
            )
        assert result.exit_code == 0, result.output
        mock_single.assert_not_called()

    def test_dry_run_alias_works(self, runner: CliRunner) -> None:
        """The deprecated ``--dry-run`` spelling still routes to preview."""
        result = runner.invoke(
            cli,
            [
                "research",
                "--dry-run",
                "-m",
                "o3-deep-research",
                "Quantum entanglement basics",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "o3-deep-research" in result.output

    def test_preview_json_output(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "research",
                "--preview",
                "--json",
                "-m",
                "o4-mini-deep-research",
                "-p",
                "openai",
                "Photonics in datacenter switching",
            ],
        )
        assert result.exit_code == 0, result.output
        # The first JSON document in the output is the preview payload.
        # Extract from the first '{' to the matching last '}'.
        start = result.output.find("{")
        end = result.output.rfind("}")
        assert start != -1 and end != -1, f"No JSON in output: {result.output!r}"
        payload = json.loads(result.output[start : end + 1])
        assert payload["preview"] is True
        assert payload["executed"] is False
        assert payload["provider"] == "openai"
        assert payload["model"] == "o4-mini-deep-research"
        ce = payload["cost_estimate"]
        assert {"min", "expected", "max"} <= set(ce.keys())
        assert 0.0 <= ce["min"] <= ce["expected"] <= ce["max"]


class TestPreviewAutoMode:
    """``--auto --preview`` shows the routing decision without spending."""

    def test_auto_preview_shows_decision(self, runner: CliRunner) -> None:
        """Auto preview prints provider/model/cost/confidence and exits."""
        # Patch the router so the test is deterministic and zero-cost.
        from deepr.routing.auto_mode import AutoModeDecision

        decision = AutoModeDecision(
            provider="xai",
            model="grok-4-1-fast-non-reasoning",
            complexity="simple",
            task_type="factual",
            cost_estimate=0.01,
            confidence=0.92,
            reasoning="Cheap factual lookup",
        )

        with patch("deepr.routing.AutoModeRouter") as mock_router_cls:
            mock_router_cls.return_value.route.return_value = decision
            result = runner.invoke(
                cli,
                ["research", "--auto", "--preview", "What is Python?"],
            )

        assert result.exit_code == 0, result.output
        out = result.output
        assert "grok-4-1-fast-non-reasoning" in out
        assert "xai" in out
        assert "92%" in out  # confidence rendered as percentage
        assert "preview only" in out.lower()

    def test_auto_preview_no_execution(self, runner: CliRunner) -> None:
        """Auto preview must not call _run_single."""
        from deepr.routing.auto_mode import AutoModeDecision

        decision = AutoModeDecision(
            provider="openai",
            model="gpt-5-mini",
            complexity="moderate",
            task_type="reasoning",
            cost_estimate=0.05,
            confidence=0.78,
            reasoning="Mid-tier reasoning",
        )

        import sys

        research_mod = sys.modules["deepr.cli.commands.semantic.research"]
        with (
            patch("deepr.routing.AutoModeRouter") as mock_router_cls,
            patch.object(research_mod, "_run_single") as mock_single,
        ):
            mock_router_cls.return_value.route.return_value = decision
            result = runner.invoke(
                cli,
                ["research", "--auto", "--preview", "Compare two designs"],
            )

        assert result.exit_code == 0, result.output
        mock_single.assert_not_called()

    def test_auto_preview_json_payload(self, runner: CliRunner) -> None:
        from deepr.routing.auto_mode import AutoModeDecision

        decision = AutoModeDecision(
            provider="openai",
            model="o3-deep-research",
            complexity="complex",
            task_type="research",
            cost_estimate=0.50,
            confidence=0.81,
            reasoning="Deep research warranted",
        )

        with patch("deepr.routing.AutoModeRouter") as mock_router_cls:
            mock_router_cls.return_value.route.return_value = decision
            result = runner.invoke(
                cli,
                ["research", "--auto", "--preview", "--json", "Survey the literature on X"],
            )

        assert result.exit_code == 0, result.output
        start = result.output.find("{")
        end = result.output.rfind("}")
        assert start != -1 and end != -1, f"No JSON in output: {result.output!r}"
        payload = json.loads(result.output[start : end + 1])
        assert payload["preview"] is True
        assert payload["executed"] is False
        assert payload["model"] == "o3-deep-research"
        assert payload["provider"] == "openai"
