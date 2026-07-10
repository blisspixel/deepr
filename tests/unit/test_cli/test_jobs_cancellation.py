"""Truthful CLI cancellation behavior."""

from unittest.mock import AsyncMock, MagicMock

import click
import pytest

import deepr.cli.commands.jobs as jobs_module
from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.research_cancellation import ResearchCancellationOutcome


def _processing_job() -> ResearchJob:
    return ResearchJob(
        id="job-1234567890",
        prompt="Research cancellation",
        status=JobStatus.PROCESSING,
        provider_job_id="provider-job-1",
    )


def _queued_job() -> ResearchJob:
    return ResearchJob(id="job-1234567890", prompt="Research cancellation")


@pytest.mark.asyncio
async def test_cli_cancel_prints_success_only_after_confirmed_closure(monkeypatch, capsys):
    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=_processing_job())
    monkeypatch.setattr(jobs_module, "SQLiteQueue", MagicMock(return_value=queue))
    monkeypatch.setattr("deepr.config.load_config", MagicMock(return_value={"provider": "openai"}))
    monkeypatch.setattr(jobs_module, "create_job_provider", MagicMock(return_value=MagicMock()))
    cancel = AsyncMock(return_value=ResearchCancellationOutcome(queue_cancelled=True, cost_closed=True))
    monkeypatch.setattr(jobs_module, "cancel_reserved_research", cancel)

    await jobs_module._cancel_job("job-1234567890")

    assert "cancelled" in capsys.readouterr().out
    cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_cli_cancel_preserves_active_state_when_provider_is_unconfirmed(monkeypatch):
    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=_processing_job())
    queue.update_status = AsyncMock()
    monkeypatch.setattr(jobs_module, "SQLiteQueue", MagicMock(return_value=queue))
    monkeypatch.setattr("deepr.config.load_config", MagicMock(return_value={"provider": "openai"}))
    monkeypatch.setattr(jobs_module, "create_job_provider", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        jobs_module,
        "cancel_reserved_research",
        AsyncMock(return_value=ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)),
    )

    with pytest.raises(click.ClickException, match="local state was unchanged"):
        await jobs_module._cancel_job("job-1234567890")

    queue.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_cli_cancel_reports_incomplete_cost_closure(monkeypatch):
    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=_processing_job())
    monkeypatch.setattr(jobs_module, "SQLiteQueue", MagicMock(return_value=queue))
    monkeypatch.setattr("deepr.config.load_config", MagicMock(return_value={"provider": "openai"}))
    monkeypatch.setattr(jobs_module, "create_job_provider", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        jobs_module,
        "cancel_reserved_research",
        AsyncMock(return_value=ResearchCancellationOutcome(queue_cancelled=True, cost_closed=False)),
    )

    with pytest.raises(click.ClickException, match="cost or cleanup closure could not be confirmed"):
        await jobs_module._cancel_job("job-1234567890")


@pytest.mark.asyncio
async def test_cli_cancel_queued_job_without_constructing_provider(monkeypatch, capsys):
    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=_queued_job())
    monkeypatch.setattr(jobs_module, "SQLiteQueue", MagicMock(return_value=queue))
    monkeypatch.setattr("deepr.config.load_config", MagicMock(return_value={"provider": "openai"}))
    provider_factory = MagicMock(side_effect=AssertionError("provider should not be constructed"))
    monkeypatch.setattr(jobs_module, "create_job_provider", provider_factory)
    monkeypatch.setattr(
        jobs_module,
        "cancel_reserved_research",
        AsyncMock(return_value=ResearchCancellationOutcome(queue_cancelled=True, cost_closed=True)),
    )

    await jobs_module._cancel_job("job-1234567890")

    assert "cancelled" in capsys.readouterr().out
    provider_factory.assert_not_called()


@pytest.mark.asyncio
async def test_cli_cancel_missing_job_is_nonzero(monkeypatch):
    queue = MagicMock(get_job=AsyncMock(return_value=None))
    monkeypatch.setattr(jobs_module, "SQLiteQueue", MagicMock(return_value=queue))

    with pytest.raises(click.ClickException, match="Job not found"):
        await jobs_module._cancel_job("missing")


@pytest.mark.asyncio
async def test_cli_cancel_terminal_job_is_nonzero(monkeypatch):
    queue = MagicMock(
        get_job=AsyncMock(
            return_value=ResearchJob(
                id="job-1234567890",
                prompt="done",
                status=JobStatus.COMPLETED,
            )
        )
    )
    monkeypatch.setattr(jobs_module, "SQLiteQueue", MagicMock(return_value=queue))

    with pytest.raises(click.ClickException, match="already completed"):
        await jobs_module._cancel_job("job-1234567890")


@pytest.mark.asyncio
async def test_cli_cancelled_job_retries_cost_closure_without_provider(monkeypatch, capsys):
    queue = MagicMock(
        get_job=AsyncMock(
            return_value=ResearchJob(
                id="job-1234567890",
                prompt="cancelled",
                status=JobStatus.CANCELLED,
                provider_job_id="provider-job",
            )
        )
    )
    monkeypatch.setattr(jobs_module, "SQLiteQueue", MagicMock(return_value=queue))
    monkeypatch.setattr("deepr.config.load_config", MagicMock(return_value={"provider": "openai"}))
    provider_factory = MagicMock(side_effect=AssertionError("provider should not be constructed"))
    monkeypatch.setattr(jobs_module, "create_job_provider", provider_factory)
    cancel = AsyncMock(return_value=ResearchCancellationOutcome(queue_cancelled=True, cost_closed=True))
    monkeypatch.setattr(jobs_module, "cancel_reserved_research", cancel)

    await jobs_module._cancel_job("job-1234567890")

    assert "cancelled" in capsys.readouterr().out
    provider_factory.assert_not_called()
    assert cancel.await_args.kwargs["provider"] is None


@pytest.mark.asyncio
async def test_cli_refresh_reports_incomplete_without_claiming_local_closure(monkeypatch, caplog):
    queue = MagicMock()
    queue.update_status = AsyncMock(return_value=True)
    provider = MagicMock()
    provider.get_status = AsyncMock(return_value=MagicMock(status="incomplete", error="secret\nforged"))
    monkeypatch.setattr("deepr.config.load_config", MagicMock(return_value={"provider": "openai"}))
    monkeypatch.setattr(jobs_module, "create_job_provider", MagicMock(return_value=provider))
    monkeypatch.setattr("deepr.storage.create_storage", MagicMock(return_value=MagicMock()))

    await jobs_module._refresh_job_statuses(queue, [_processing_job()])

    queue.update_status.assert_not_awaited()
    assert "awaits lifecycle reconciliation" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.asyncio
async def test_cli_refresh_logs_exception_type_without_content(monkeypatch, caplog):
    provider = MagicMock()
    provider.get_status = AsyncMock(side_effect=RuntimeError("secret\nforged"))
    monkeypatch.setattr("deepr.config.load_config", MagicMock(return_value={"provider": "openai"}))
    monkeypatch.setattr(jobs_module, "create_job_provider", MagicMock(return_value=provider))
    monkeypatch.setattr("deepr.storage.create_storage", MagicMock(return_value=MagicMock()))

    await jobs_module._refresh_job_statuses(MagicMock(), [_processing_job()])

    assert "RuntimeError" in caplog.text
    assert "secret" not in caplog.text
