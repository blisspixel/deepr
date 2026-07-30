"""Security tests for Azure blob report namespace validation."""

from datetime import UTC, datetime

import pytest

from deepr.services.research_bounds import ResearchRequestBoundsError
from deepr.storage.base import StorageError
from deepr.storage.blob import AzureBlobStorage, BlobServiceClient


def _storage_without_client() -> AzureBlobStorage:
    return AzureBlobStorage.__new__(AzureBlobStorage)


def test_blob_constructor_blocks_before_cloud_client_creation(monkeypatch):
    monkeypatch.setattr(
        BlobServiceClient,
        "from_connection_string",
        lambda *_args, **_kwargs: pytest.fail("cloud client must not be constructed"),
    )

    with pytest.raises(ResearchRequestBoundsError) as exc_info:
        AzureBlobStorage(connection_string="DefaultEndpointsProtocol=https;AccountName=untrusted")

    assert exc_info.value.code == "research_file_storage_unbounded"


class _FakeBlob:
    def __init__(self, name: str):
        self.name = name
        self.size = 1
        self.last_modified = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeContainer:
    url = "https://example.blob.core.windows.net/reports"

    def __init__(self, names: list[str]):
        self._names = names

    async def list_blobs(self, name_starts_with: str = ""):
        for name in self._names:
            if name.startswith(name_starts_with):
                yield _FakeBlob(name)


def test_blob_name_uses_validated_job_id_and_filename():
    storage = _storage_without_client()

    assert storage._get_blob_name("job-abc_123", "report.md") == "job-abc_123/report.md"


@pytest.mark.parametrize(
    "job_id",
    [
        "",
        "   ",
        "../secret",
        "..\\secret",
        "job/subdir",
        "job\\subdir",
        "job/../../secret",
    ],
)
def test_blob_job_id_rejects_namespace_escape(job_id: str):
    storage = _storage_without_client()

    with pytest.raises(StorageError):
        storage._get_blob_name(job_id, "report.md")


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "   ",
        ".",
        "..",
        "bad\x00.txt",
        "../secret.txt",
        "..\\secret.txt",
        "subdir/file.txt",
        "subdir\\file.txt",
        "valid..txt",
    ],
)
def test_blob_filename_rejects_path_components(filename: str):
    storage = _storage_without_client()

    with pytest.raises(StorageError):
        storage._get_blob_name("job-123", filename)


@pytest.mark.asyncio
async def test_blob_list_blocks_before_existing_container_use():
    storage = _storage_without_client()
    storage.container_client = _FakeContainer(
        [
            "job-1/report.md",
            "job-2/subdir/report.md",
            "../bad/report.md",
            "job-3/valid..txt",
            "noslash",
        ]
    )

    with pytest.raises(ResearchRequestBoundsError) as exc_info:
        await storage.list_reports()

    assert exc_info.value.code == "research_file_storage_unbounded"
