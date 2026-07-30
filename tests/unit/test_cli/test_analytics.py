"""Regression tests for analytics CLI reporting."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.commands.analytics import analytics


def test_report_reads_monthly_budget_from_loaded_config(monkeypatch):
    """A populated report must use the loaded config without a NameError."""
    now = datetime.now(UTC)
    job = SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        submitted_at=now - timedelta(minutes=2),
        completed_at=now,
        model="local-test-model",
        cost=4.50,
    )

    monkeypatch.setattr("deepr.config.load_config", lambda: {"max_monthly_cost": 5.0})
    monkeypatch.setattr("deepr.queue.create_queue", lambda *_args, **_kwargs: object())

    def complete_without_queue(operation):
        operation.close()
        return [job]

    monkeypatch.setattr(
        "deepr.cli.commands.analytics.run_async_command",
        complete_without_queue,
    )

    result = CliRunner().invoke(analytics, ["report", "--period", "month"])

    assert result.exit_code == 0, result.output
    assert "Approaching monthly budget limit" in result.output
    assert "Limit: $5.00" in result.output
