"""Security tests for Azure blob report namespace validation."""

from datetime import UTC, datetime

import pytest

from deepr.storage.base import StorageError
from deepr.storage.blob import AzureBlobStorage


def _storage_without_client() -> AzureBlobStorage:
    return AzureBlobStorage.__new__(AzureBlobStorage)


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
async def test_list_reports_skips_malformed_legacy_blob_names():
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

    reports = await storage.list_reports()

    assert [(report.job_id, report.filename) for report in reports] == [("job-1", "report.md")]
