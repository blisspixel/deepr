"""Tests for the public job-metadata trust boundary."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.queue.base import ResearchJob, client_job_metadata, public_job_metadata


def test_client_job_metadata_preserves_annotations() -> None:
    metadata = {"campaign": "launch", "nested": {"priority": 2}}

    assert client_job_metadata(metadata) == metadata
    assert client_job_metadata(metadata) is not metadata


@pytest.mark.parametrize(
    "reserved_key",
    [
        "cleanup_vector_store",
        "cost_reservation_estimated_usd",
        "cost_reservation_id",
        "cost_reservation_model",
        "cost_reservation_provider",
        "provider_file_ids",
        "uploaded_files",
        "vector_store_id",
    ],
)
def test_client_job_metadata_rejects_provider_lifecycle_fields(reserved_key: str) -> None:
    with pytest.raises(ValueError, match="metadata contains reserved fields"):
        client_job_metadata({reserved_key: "client-selected"})


def test_client_job_metadata_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="metadata must be an object"):
        client_job_metadata(["not", "an", "object"])


def test_public_job_metadata_redacts_lifecycle_fields() -> None:
    metadata = {
        "campaign": "launch",
        "cost_reservation_id": "reservation-private",
        "provider_file_ids": ["file-private"],
        "vector_store_id": "vs-private",
    }

    assert public_job_metadata(metadata) == {"campaign": "launch"}


def test_research_job_websocket_projection_redacts_lifecycle_fields() -> None:
    job = ResearchJob(
        id="job-1",
        prompt="Research metadata boundaries",
        metadata={"campaign": "launch", "provider_file_ids": ["file-private"]},
    )

    assert job.to_dict()["metadata"] == {"campaign": "launch"}


@pytest.mark.asyncio
async def test_trusted_internal_metadata_still_drives_own_job_cleanup() -> None:
    from deepr.cli.commands.run_submission import cleanup_persisted_uploads

    provider = MagicMock()
    provider.delete_document = AsyncMock(return_value=True)
    provider.delete_vector_store = AsyncMock(return_value=True)
    job = ResearchJob(
        id="job-1",
        prompt="Research metadata boundaries",
        metadata={
            "provider_file_ids": ["file-owned-by-job-1"],
            "vector_store_id": "vs-owned-by-job-1",
        },
    )

    assert await cleanup_persisted_uploads(provider, job) is True
    provider.delete_document.assert_awaited_once_with("file-owned-by-job-1")
    provider.delete_vector_store.assert_awaited_once_with("vs-owned-by-job-1")
