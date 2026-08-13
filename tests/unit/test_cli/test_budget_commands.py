"""Unit tests for budget CLI commands - no API calls.

Tests the budget command structure, parameter validation, and display logic
without making any external API calls.
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.commands.budget import _next_month_start
from deepr.cli.main import cli
from deepr.experts.research_reservation_store import ReconciledResearchExposure
from deepr.observability import provider_account_controls as account_controls_module
from deepr.observability.provider_account_controls import (
    PaidApiAccountEvidence,
    ProviderAccountBinding,
    ProviderAccountEvidenceStore,
)

_TEST_AUTHORIZATION = {
    "authority": "verified_by_deepr",
    "evidence_ids": ["verified-unit-test-control"],
    "valid_until": "2099-01-01T00:00:00+00:00",
}


def _recovery_evidence(*, freeze_id: str = "freeze-cli-test") -> tuple[str, str]:
    observed_at = datetime.now(UTC)
    store = ProviderAccountEvidenceStore()
    base_evidence = next(
        evidence
        for path in (store.root / "account_evidence").glob("*.json")
        if (evidence := store.load(path.stem)).provider == "openai"
    )
    evidence = PaidApiAccountEvidence(
        schema_version="deepr-paid-api-account-evidence-v1",
        kind="deepr.costs.paid_api_account_evidence",
        provider="openai",
        account_id="test-openai-account",
        scope_ref="test-openai-scope",
        credential_fingerprint="sha256:" + "3" * 64,
        freeze_id=freeze_id,
        freeze_frozen_at=observed_at.isoformat(),
        observed_at=observed_at.isoformat(),
        valid_until=(observed_at + timedelta(hours=1)).isoformat(),
        source_posture="provider_api",
        source_evidence_sha256=base_evidence.source_evidence_sha256,
        billing_reconciliation_sha256=base_evidence.billing_reconciliation_sha256,
        control_mode="hard_monthly_limit",
        currency="USD",
        overage_enabled=False,
        hard_monthly_limit_usd="5.00",
    )
    evidence_id, _path = store.store(evidence)
    return evidence_id, observed_at.isoformat()


class TestBudgetCommandStructure:
    """Test budget command structure and help text."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_command_exists(self, runner):
        """Test that 'budget' command exists."""
        result = runner.invoke(cli, ["budget", "--help"])
        assert result.exit_code == 0
        assert "budget" in result.output.lower()

    def test_budget_command_shows_subcommands(self, runner):
        """Test that budget command lists subcommands."""
        result = runner.invoke(cli, ["budget", "--help"])
        assert result.exit_code == 0

        output = result.output.lower()
        # Should have set and status subcommands
        assert "set" in output
        assert "status" in output


class TestBudgetSetCommand:
    """Test 'budget set' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_set_help(self, runner):
        """Test that 'budget set' help works."""
        result = runner.invoke(cli, ["budget", "set", "--help"])
        assert result.exit_code == 0

    def test_budget_set_requires_amount(self, runner):
        """Test that 'budget set' requires an amount."""
        result = runner.invoke(cli, ["budget", "set"])
        # Should fail or show error about missing amount
        assert result.exit_code != 0

    def test_budget_set_accepts_amount(self, runner):
        """Test that 'budget set' accepts an amount argument."""
        result = runner.invoke(cli, ["budget", "set", "10.00"])
        assert result.exit_code == 0

    def test_next_reset_is_the_next_calendar_month(self):
        assert _next_month_start(datetime(2026, 7, 29, 12, tzinfo=UTC)) == datetime(2026, 8, 1, tzinfo=UTC)
        assert _next_month_start(datetime(2026, 12, 31, 23, tzinfo=UTC)) == datetime(2027, 1, 1, tzinfo=UTC)

    def test_budget_set_validates_numeric_amount(self, runner):
        """Test that 'budget set' validates numeric amounts."""
        result = runner.invoke(cli, ["budget", "set", "abc"])
        # Should reject non-numeric amounts
        assert result.exit_code != 0

    def test_budget_set_zero_freezes_paid_api(self, runner):
        """Test that 'budget set 0' creates a hard paid freeze."""
        result = runner.invoke(cli, ["budget", "set", "0"])
        assert result.exit_code == 0
        assert "paid api dispatch frozen" in result.output.lower()

    def test_zero_then_positive_budget_remains_frozen(self, runner):
        assert runner.invoke(cli, ["budget", "set", "0"]).exit_code == 0
        assert runner.invoke(cli, ["budget", "set", "10"]).exit_code == 0

        result = runner.invoke(cli, ["budget", "status"])

        assert result.exit_code == 0
        assert "Mode: Paid API frozen" in result.output
        assert "Effective monthly ceiling: $0.00" in result.output

    def test_budget_set_rejects_unlimited(self, runner):
        """Unlimited paid autonomy is not a valid budget state."""
        result = runner.invoke(cli, ["budget", "set", "--", "-1"])
        assert result.exit_code == 2
        assert "not in the range" in result.output.lower()


class TestBudgetStatusCommand:
    """Test 'budget status' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_status_exists(self, runner):
        """Test that budget status command exists."""
        result = runner.invoke(cli, ["budget", "status", "--help"])
        assert result.exit_code == 0

    def test_budget_status_shows_info(self, runner):
        """Test that 'budget status' shows budget information."""
        with patch("deepr.cli.commands.budget.load_budget_config") as mock_load:
            mock_load.return_value = {
                "monthly_limit": 50.0,
                "monthly_spending": 10.0,
                "current_month": "2026-01",
                "paid_api_authorization": _TEST_AUTHORIZATION,
            }
            result = runner.invoke(cli, ["budget", "status"])
            assert result.exit_code == 0
            # Should show budget info
            assert "$" in result.output

    def test_budget_status_displays_effective_tighter_authority(self, runner):
        with (
            patch(
                "deepr.cli.commands.budget.load_budget_config",
                return_value={
                    "monthly_limit": 50.0,
                    "monthly_spending": 2.0,
                    "current_month": "2026-07",
                    "paid_api_authorization": _TEST_AUTHORIZATION,
                },
            ),
            patch("deepr.cli.commands.budget.resolve_spend_caps", return_value={"monthly": 10.0}),
            patch(
                "deepr.cli.commands.budget._atomic_monthly_exposure",
                return_value=SimpleNamespace(monthly_settled_cost=2.0, active_cost=0.0),
            ),
        ):
            result = runner.invoke(cli, ["budget", "status"])

        assert result.exit_code == 0
        assert "$2.00 / $10.00" in result.output
        assert "Configured monthly budget: $50.00; tighter policy is active" in result.output

    def test_budget_status_counts_active_holds_in_exposure(self, runner):
        with (
            patch(
                "deepr.cli.commands.budget.load_budget_config",
                return_value={
                    "monthly_limit": 10.0,
                    "monthly_spending": 0.0,
                    "current_month": "2026-07",
                    "paid_api_authorization": _TEST_AUTHORIZATION,
                },
            ),
            patch("deepr.cli.commands.budget.resolve_spend_caps", return_value={"monthly": 10.0}),
            patch(
                "deepr.cli.commands.budget._atomic_monthly_exposure",
                return_value=SimpleNamespace(monthly_settled_cost=2.0, active_cost=0.5),
            ),
        ):
            result = runner.invoke(cli, ["budget", "status"])

        assert result.exit_code == 0
        assert "Settled this month: $2.00" in result.output
        assert "Active durable holds: $0.50" in result.output
        assert "Budget: $2.50 / $10.00" in result.output
        assert "Remaining: $7.50" in result.output

    def test_budget_status_shows_total_attended_grant_drawdown(self, runner):
        from deepr.core.cost_caps import OperatorBudget

        with (
            patch(
                "deepr.cli.commands.budget.load_budget_config",
                return_value={"monthly_limit": 50.0, "monthly_spending": 19.0, "current_month": "2026-08"},
            ),
            patch("deepr.cli.commands.budget.resolve_spend_caps", return_value={"monthly": 2.0}),
            patch(
                "deepr.cli.commands.budget.read_operator_budget_for_status",
                return_value=OperatorBudget(
                    configured=True,
                    monthly_limit=2.0,
                    frozen=False,
                    attended_grant_id="grant-test",
                    attended_grant_expires_at="2026-08-12T12:30:00+00:00",
                    attended_grant_amount_usd=2.0,
                    attended_grant_settled_baseline_usd=41.0,
                ),
            ),
            patch(
                "deepr.cli.commands.budget._atomic_monthly_exposure",
                return_value=SimpleNamespace(
                    monthly_settled_cost=19.0,
                    total_settled_cost=41.25,
                    active_cost=0.5,
                ),
            ),
        ):
            result = runner.invoke(cli, ["budget", "status"])

        assert result.exit_code == 0
        assert "Mode: Attended paid API grant" in result.output
        assert "Settled since grant: $0.25" in result.output
        assert "API grant: $0.75 / $2.00" in result.output
        assert "Remaining: $1.25" in result.output
        assert "does not draw down this grant" in result.output

    def test_budget_status_fails_closed_when_holds_are_unreadable(self, runner):
        with (
            patch(
                "deepr.cli.commands.budget.load_budget_config",
                return_value={
                    "monthly_limit": 10.0,
                    "monthly_spending": 0.0,
                    "current_month": "2026-07",
                    "paid_api_authorization": _TEST_AUTHORIZATION,
                },
            ),
            patch("deepr.cli.commands.budget.resolve_spend_caps", return_value={"monthly": 10.0}),
            patch("deepr.cli.commands.budget._atomic_monthly_exposure", return_value=None),
        ):
            result = runner.invoke(cli, ["budget", "status"])

        assert result.exit_code == 0
        assert "Active durable holds: UNKNOWN" in result.output
        assert "Paid API blocked" in result.output
        assert "Remaining: $0.00 (fail closed)" in result.output


class TestBudgetHistoryCommand:
    """Test 'budget history' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_history_exists(self, runner):
        """Test that budget history command exists."""
        result = runner.invoke(cli, ["budget", "history", "--help"])
        assert result.exit_code == 0

    def test_budget_history_limit_option(self, runner):
        """Test that --limit option exists."""
        result = runner.invoke(cli, ["budget", "history", "--help"])
        assert "--limit" in result.output or "-n" in result.output

    def test_budget_history_reads_canonical_ledger(self, runner):
        event = SimpleNamespace(
            timestamp=datetime(2026, 7, 1, 0, 22, tzinfo=UTC),
            cost_usd=1.25,
            provider="openai",
            model="gpt-5",
            operation="research_completion",
            source="test.canonical",
            task_id="research_job-123",
            session_id="",
        )
        ledger = MagicMock()
        ledger.with_locked_accounting_events.side_effect = lambda operation: operation([event])

        with (
            patch("deepr.observability.cost_ledger.CostLedger", return_value=ledger),
            patch("deepr.cli.commands.budget._durable_active_cost", return_value=0.5),
        ):
            result = runner.invoke(cli, ["budget", "history"])

        assert result.exit_code == 0
        assert "openai/gpt-5" in result.output
        assert "research_completion | test.canonical | research_job-123" in result.output
        assert "Total all-time settled spending: $1.250000" in result.output
        assert "Active durable holds: $0.500000" in result.output

    def test_budget_history_fails_closed_when_ledger_is_unreadable(self, runner):
        ledger = MagicMock()
        ledger.with_locked_accounting_events.side_effect = OSError("ledger unavailable")

        with patch("deepr.observability.cost_ledger.CostLedger", return_value=ledger):
            result = runner.invoke(cli, ["budget", "history"])

        assert result.exit_code == 1
        assert "Canonical cost ledger is unreadable" in result.output


class TestBudgetSafetyCommand:
    """Test 'budget safety' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_safety_exists(self, runner):
        """Test that budget safety command exists."""
        result = runner.invoke(cli, ["budget", "safety", "--help"])
        assert result.exit_code == 0

    def test_budget_safety_shows_limits(self, runner):
        """Test that budget safety shows cost limits."""
        result = runner.invoke(cli, ["budget", "safety"])
        output = result.output.lower()
        # Should mention limits or safety
        assert "limit" in output or "safety" in output or "daily" in output


class TestBudgetFreezeCommands:
    """Manual freezes cannot be cleared without proven headroom."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_freeze_persists_fail_closed_state(self, runner):
        config = {"monthly_limit": 10.0, "monthly_spending": 2.0}

        def mutate(callback):
            callback(config)
            return config

        with patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate):
            result = runner.invoke(cli, ["budget", "freeze", "--reason", "operator stop"])

        assert result.exit_code == 0
        assert config["paid_api_frozen"] is True
        assert config["freeze_reason"] == "operator stop"

    def test_unfreeze_refuses_exhausted_month(self, runner):
        evidence_id, frozen_at = _recovery_evidence()
        config = {
            "monthly_limit": 10.0,
            "monthly_spending": 9.0,
            "paid_api_frozen": True,
            "freeze_reason": "operator stop",
            "freeze_id": "freeze-cli-test",
            "freeze_kind": "manual",
            "frozen_at": frozen_at,
        }

        def mutate(callback):
            callback(config)
            return config

        with (
            patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate),
            patch(
                "deepr.cli.commands.budget._atomic_monthly_exposure",
                return_value=ReconciledResearchExposure(
                    daily_settled_cost=10.0,
                    weekly_settled_cost=10.0,
                    monthly_settled_cost=10.0,
                    total_settled_cost=10.0,
                    active_cost=0.0,
                    unresolved_cost=0.0,
                    unresolved_count=0,
                ),
            ),
        ):
            result = runner.invoke(cli, ["budget", "unfreeze", "--evidence-id", evidence_id])

        assert result.exit_code == 1
        assert "exhausted" in result.output.lower()
        assert config["paid_api_frozen"] is True

    def test_unfreeze_requires_readable_canonical_ledger(self, runner):
        evidence_id, frozen_at = _recovery_evidence()
        config = {
            "monthly_limit": 10.0,
            "monthly_spending": 1.0,
            "paid_api_frozen": True,
            "freeze_reason": "operator stop",
            "freeze_id": "freeze-cli-test",
            "freeze_kind": "manual",
            "frozen_at": frozen_at,
        }

        original = dict(config)

        def mutate(callback):
            callback(config)
            return config

        with (
            patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate),
            patch("deepr.cli.commands.budget._atomic_monthly_exposure", return_value=None),
        ):
            result = runner.invoke(cli, ["budget", "unfreeze", "--evidence-id", evidence_id])

        assert result.exit_code == 1
        assert "unreadable" in result.output.lower()
        assert config == original

    def test_unfreeze_rejects_evidence_for_an_older_ledger_snapshot(self, runner):
        from deepr.observability.cost_ledger import CostLedger

        evidence_id, frozen_at = _recovery_evidence()
        config = {
            "monthly_limit": 10.0,
            "monthly_spending": 0.0,
            "paid_api_frozen": True,
            "freeze_reason": "operator stop",
            "freeze_id": "freeze-cli-test",
            "freeze_kind": "manual",
            "frozen_at": frozen_at,
        }
        CostLedger().record_event(
            operation="research_completion",
            provider="openai",
            cost_usd=0.25,
            idempotency_key="unfreeze-ledger-changed",
        )

        def mutate(callback):
            callback(config)
            return config

        with (
            patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate),
            patch(
                "deepr.cli.commands.budget._atomic_monthly_exposure",
                return_value=ReconciledResearchExposure(
                    daily_settled_cost=0.25,
                    weekly_settled_cost=0.25,
                    monthly_settled_cost=0.25,
                    total_settled_cost=0.25,
                    active_cost=0.0,
                    unresolved_cost=0.0,
                    unresolved_count=0,
                ),
            ),
        ):
            result = runner.invoke(cli, ["budget", "unfreeze", "--evidence-id", evidence_id])

        assert result.exit_code == 1
        assert "no longer binds the current strict ledger snapshot" in result.output
        assert config["paid_api_frozen"] is True

    def test_unfreeze_succeeds_only_with_positive_headroom(self, runner):
        evidence_id, frozen_at = _recovery_evidence()
        config = {
            "monthly_limit": 10.0,
            "monthly_spending": 1.0,
            "paid_api_frozen": True,
            "freeze_reason": "operator stop",
            "freeze_id": "freeze-cli-test",
            "freeze_kind": "manual",
            "frozen_at": frozen_at,
        }

        def mutate(callback):
            callback(config)
            return config

        with (
            patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate),
            patch(
                "deepr.cli.commands.budget._atomic_monthly_exposure",
                return_value=ReconciledResearchExposure(
                    daily_settled_cost=2.0,
                    weekly_settled_cost=2.0,
                    monthly_settled_cost=2.0,
                    total_settled_cost=2.0,
                    active_cost=0.0,
                    unresolved_cost=0.0,
                    unresolved_count=0,
                ),
            ),
        ):
            result = runner.invoke(cli, ["budget", "unfreeze", "--evidence-id", evidence_id])

        assert result.exit_code == 0
        assert config["paid_api_frozen"] is False
        assert config["freeze_reason"] == ""
        assert "frozen_at" not in config
        assert config["paid_api_authorization"]["evidence_ids"] == [evidence_id]

    def test_unfreeze_validates_current_account_scope_and_credential(self, runner, monkeypatch):
        evidence_id, frozen_at = _recovery_evidence()
        config = {
            "monthly_limit": 10.0,
            "monthly_spending": 0.0,
            "paid_api_frozen": True,
            "freeze_reason": "operator stop",
            "freeze_id": "freeze-cli-test",
            "freeze_kind": "manual",
            "frozen_at": frozen_at,
        }

        def mutate(callback):
            callback(config)
            return config

        monkeypatch.setattr(
            account_controls_module,
            "_resolve_current_provider_account_binding",
            lambda provider: ProviderAccountBinding(
                provider=provider,
                account_id="wrong-account",
                scope_ref="test-openai-scope",
                credential_fingerprint="sha256:" + "3" * 64,
            ),
        )
        with patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate):
            result = runner.invoke(cli, ["budget", "unfreeze", "--evidence-id", evidence_id])

        assert result.exit_code == 1
        assert "does not match" in result.output
        assert config["paid_api_frozen"] is True

    def test_concurrent_record_and_limit_update_cannot_clear_freeze(self):
        from deepr.cli.commands.budget import load_budget_config, mutate_budget_config, record_spending

        def freeze_update():
            def update(config):
                config["paid_api_frozen"] = True
                config["freeze_reason"] = "concurrency test"

            mutate_budget_config(update)

        def limit_update():
            mutate_budget_config(lambda config: config.__setitem__("monthly_limit", 10.0))

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(freeze_update),
                executor.submit(limit_update),
                executor.submit(record_spending, 0.25, "job-race", "race test"),
            ]
            for future in futures:
                future.result(timeout=2)

        config = load_budget_config()
        assert config["paid_api_frozen"] is True
        assert config["monthly_limit"] == 10.0
        assert config["monthly_spending"] == pytest.approx(0.25)
        assert config["history"][-1]["job_id"] == "job-race"


class TestBudgetValidation:
    """Test budget validation logic."""

    def test_validate_budget_accepts_valid_amounts(self):
        """Test that validation accepts valid budget amounts without confirmation."""
        from deepr.cli.validation import validate_budget

        # Should accept amounts below warn threshold without prompting
        assert validate_budget(5.0) == 5.0
        assert validate_budget(0.5) == 0.5

    def test_validate_budget_rejects_negative(self):
        """Test that validation rejects negative amounts (except -1 for unlimited)."""
        import click

        from deepr.cli.validation import validate_budget

        # Negative amounts below min_budget should be rejected
        with pytest.raises(click.UsageError):
            validate_budget(-5.0, min_budget=0.0)

    def test_validate_budget_accepts_zero_with_zero_min(self):
        """Test that validation accepts zero when min_budget is 0."""
        from deepr.cli.validation import validate_budget

        # Zero should be accepted when min_budget is 0
        assert validate_budget(0.0, min_budget=0.0) == 0.0

    def test_validate_budget_rejects_below_min(self):
        """Test that validation rejects amounts below min_budget."""
        import click

        from deepr.cli.validation import validate_budget

        with pytest.raises(click.UsageError):
            validate_budget(0.1, min_budget=0.5)

    def test_validate_budget_accepts_at_min(self):
        """Test that validation accepts amounts at min_budget."""
        from deepr.cli.validation import validate_budget

        assert validate_budget(0.5, min_budget=0.5) == 0.5

    @pytest.mark.parametrize("invalid", [True, -0.01, float("inf"), float("nan")])
    def test_record_spending_rejects_invalid_cost(self, invalid):
        from deepr.cli.commands.budget import record_spending

        with pytest.raises(ValueError, match="finite non-negative"):
            record_spending(invalid, "job", "invalid")


class TestBudgetDisplay:
    """Test budget display formatting."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_status_displays_currency_format(self, runner):
        """Test that budget status displays amounts in currency format."""
        with patch("deepr.cli.commands.budget.load_budget_config") as mock_load:
            mock_load.return_value = {
                "monthly_limit": 50.0,
                "monthly_spending": 10.0,
                "current_month": "2026-01",
                "paid_api_authorization": _TEST_AUTHORIZATION,
            }
            result = runner.invoke(cli, ["budget", "status"])

            # Should display dollar amounts
            assert "$" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
