"""Regression test: a provider-failed job must transition to FAILED locally.

The provider status response carries `error` as an SDK object, not a string.
`_get_results` previously passed that object straight into
`queue.update_status(..., error=...)`; the SQLite parameter bind raised, the
generic exception handler swallowed it, and the job stayed "processing" forever
with its cost reservation open. The fix coerces the error to `str` first.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.cli.commands import status as status_module
from deepr.queue.base import JobStatus


class _ProviderErrorObject:
    """Stands in for an SDK error type that SQLite cannot bind."""

    def __str__(self) -> str:
        return "insufficient_quota: you exceeded your current quota"


@pytest.mark.asyncio
async def test_provider_failed_job_is_marked_failed_with_string_error(monkeypatch: pytest.MonkeyPatch) -> None:
    job = MagicMock()
    job.id = "research-test123"
    job.status = JobStatus.PROCESSING
    job.provider_job_id = "resp_abc"
    job.provider = "openai"
    job.model = "gpt-5-mini"

    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=job)
    queue.update_status = AsyncMock(return_value=True)

    response = MagicMock()
    response.status = "failed"
    response.error = _ProviderErrorObject()

    provider = MagicMock()
    provider.get_status = AsyncMock(return_value=response)

    with (
        patch.object(status_module, "SQLiteQueue", return_value=queue),
        patch("deepr.providers.create_provider", return_value=provider),
        patch("deepr.config.load_config", return_value={"api_key": "test-key"}),
    ):
        await status_module._get_results("research-test123")

    queue.update_status.assert_awaited_once()
    args, kwargs = queue.update_status.await_args
    assert args[1] is JobStatus.FAILED
    # The regression: this must be a plain string, never the SDK object, or the
    # SQLite bind fails and the job is stuck processing forever.
    assert isinstance(kwargs["error"], str)
    assert "insufficient_quota" in kwargs["error"]
