"""Azure Blob Storage implementation."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient, ContainerClient

from deepr.utils.security import InvalidInputError, PathTraversalError, sanitize_name

from .base import ReportMetadata, StorageBackend, StorageError


class AzureBlobStorage(StorageBackend):
    """Azure Blob Storage implementation of storage backend."""

    def __init__(
        self,
        connection_string: str | None = None,
        account_url: str | None = None,
        container_name: str = "reports",
        use_managed_identity: bool = False,
    ):
        """
        Initialize Azure Blob Storage.

        Args:
            connection_string: Azure Storage connection string
            account_url: Azure Storage account URL (for managed identity)
            container_name: Name of the blob container
            use_managed_identity: Use Azure Managed Identity for authentication
        """
        self.container_name = container_name

        if use_managed_identity:
            # Use Azure Managed Identity
            from azure.identity.aio import DefaultAzureCredential

            if not account_url:
                account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
            if not account_url:
                raise ValueError("account_url or AZURE_STORAGE_ACCOUNT_URL required for managed identity")

            credential = DefaultAzureCredential()
            self.client = BlobServiceClient(account_url=account_url, credential=credential)
        else:
            # Use connection string
            connection_string = connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if not connection_string:
                raise ValueError("connection_string or AZURE_STORAGE_CONNECTION_STRING environment variable required")

            self.client = BlobServiceClient.from_connection_string(connection_string)

        self.container_client: ContainerClient | None = None

    async def _ensure_container(self) -> None:
        """Ensure container exists, create if necessary."""
        if self.container_client is None:
            self.container_client = self.client.get_container_client(self.container_name)
            try:
                await self.container_client.get_container_properties()
            except ResourceNotFoundError:
                # Container doesn't exist, create it
                await self.container_client.create_container()

    async def _container(self) -> ContainerClient:
        """Return an initialized container client."""
        await self._ensure_container()
        if self.container_client is None:
            raise StorageError(
                message="Blob container client is not initialized",
                storage_type="blob",
                original_error=None,
            )
        return self.container_client

    def _get_blob_name(self, job_id: str, filename: str) -> str:
        """Generate blob name from job_id and filename."""
        return f"{self._validate_job_id(job_id)}/{self._validate_filename(filename)}"

    def _validate_job_id(self, job_id: str) -> str:
        """Validate job_id before using it as a blob namespace prefix."""
        try:
            if ".." in job_id or "/" in job_id or "\\" in job_id:
                raise PathTraversalError(f"Invalid job_id contains path traversal: {job_id}")
            return sanitize_name(job_id, allowed_chars=r"a-zA-Z0-9_-")
        except (PathTraversalError, InvalidInputError) as e:
            raise StorageError(message=f"Invalid job_id: {e!s}", storage_type="blob", original_error=e) from e

    def _validate_filename(self, filename: str) -> str:
        """Validate a report filename before using it in a blob name."""
        if not filename or not filename.strip() or filename in {".", ".."} or "\x00" in filename:
            raise StorageError(
                message=f"Invalid filename: {filename!r}",
                storage_type="blob",
                original_error=None,
            )
        if "/" in filename or "\\" in filename or ".." in filename:
            raise StorageError(
                message=f"Invalid filename contains path components: {filename}",
                storage_type="blob",
                original_error=None,
            )
        return filename

    async def save_report(
        self,
        job_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ReportMetadata:
        """Save report to Azure Blob Storage."""
        try:
            container = await self._container()

            validated_job_id = self._validate_job_id(job_id)
            validated_filename = self._validate_filename(filename)
            blob_name = self._get_blob_name(validated_job_id, validated_filename)
            blob_client = container.get_blob_client(blob_name)

            # Prepare blob metadata
            blob_metadata = dict(metadata or {})
            blob_metadata["job_id"] = validated_job_id
            blob_metadata["filename"] = validated_filename

            # Upload blob
            await blob_client.upload_blob(content, content_type=content_type, metadata=blob_metadata, overwrite=True)

            # Get blob properties
            props = await blob_client.get_blob_properties()

            # Determine format from filename
            format_ext = validated_filename.split(".")[-1] if "." in validated_filename else ""

            return ReportMetadata(
                job_id=validated_job_id,
                filename=validated_filename,
                format=format_ext,
                size_bytes=props.size,
                created_at=props.last_modified.replace(tzinfo=UTC),
                url=blob_client.url,
                content_type=content_type,
            )

        except AzureError as e:
            raise StorageError(
                message=f"Failed to save report to blob storage: {e!s}",
                storage_type="blob",
                original_error=e,
            ) from e

    async def get_report(self, job_id: str, filename: str) -> bytes:
        """Retrieve report from Azure Blob Storage."""
        try:
            container = await self._container()

            blob_name = self._get_blob_name(job_id, filename)
            blob_client = container.get_blob_client(blob_name)

            # Download blob
            stream = await blob_client.download_blob()
            content = await stream.readall()

            return bytes(content)

        except ResourceNotFoundError:
            raise StorageError(
                message=f"Report not found: {job_id}/{filename}",
                storage_type="blob",
                original_error=None,
            ) from None
        except AzureError as e:
            raise StorageError(
                message=f"Failed to retrieve report from blob storage: {e!s}",
                storage_type="blob",
                original_error=e,
            ) from e

    async def list_reports(self, job_id: str | None = None) -> list[ReportMetadata]:
        """List reports in Azure Blob Storage."""
        try:
            container = await self._container()

            reports: list[ReportMetadata] = []
            prefix = f"{self._validate_job_id(job_id)}/" if job_id else ""

            async for blob in container.list_blobs(name_starts_with=prefix):
                # Parse job_id and filename from blob name
                parts = blob.name.split("/", 1)
                if len(parts) == 2:
                    blob_job_id, blob_filename = parts
                else:
                    continue

                try:
                    blob_job_id = self._validate_job_id(blob_job_id)
                    blob_filename = self._validate_filename(blob_filename)
                except StorageError:
                    continue

                # Determine format
                format_ext = blob_filename.split(".")[-1] if "." in blob_filename else ""

                reports.append(
                    ReportMetadata(
                        job_id=blob_job_id,
                        filename=blob_filename,
                        format=format_ext,
                        size_bytes=blob.size,
                        created_at=blob.last_modified.replace(tzinfo=UTC),
                        url=f"{container.url}/{blob.name}",
                        content_type=self.get_content_type(blob_filename),
                    )
                )

            return reports

        except AzureError as e:
            raise StorageError(
                message=f"Failed to list reports in blob storage: {e!s}",
                storage_type="blob",
                original_error=e,
            ) from e

    async def delete_report(self, job_id: str, filename: str | None = None) -> bool:
        """Delete report(s) from Azure Blob Storage."""
        try:
            container = await self._container()

            if filename:
                # Delete specific blob
                blob_name = self._get_blob_name(job_id, filename)
                blob_client = container.get_blob_client(blob_name)
                await blob_client.delete_blob()
                return True
            else:
                # Delete all blobs for this job
                deleted = False
                prefix = f"{self._validate_job_id(job_id)}/"
                async for blob in container.list_blobs(name_starts_with=prefix):
                    blob_client = container.get_blob_client(blob.name)
                    await blob_client.delete_blob()
                    deleted = True
                return deleted

        except ResourceNotFoundError:
            return False
        except AzureError as e:
            raise StorageError(
                message=f"Failed to delete report from blob storage: {e!s}",
                storage_type="blob",
                original_error=e,
            ) from e

    async def report_exists(self, job_id: str, filename: str) -> bool:
        """Check if report exists in Azure Blob Storage."""
        try:
            container = await self._container()

            blob_name = self._get_blob_name(job_id, filename)
            blob_client = container.get_blob_client(blob_name)

            await blob_client.get_blob_properties()
            return True

        except ResourceNotFoundError:
            return False
        except AzureError:
            return False

    async def get_report_url(self, job_id: str, filename: str, expires_in: int = 3600) -> str:
        """Get signed URL for report access."""
        try:
            container = await self._container()

            blob_name = self._get_blob_name(job_id, filename)
            blob_client = container.get_blob_client(blob_name)

            # Generate SAS token for time-limited access
            from azure.storage.blob import BlobSasPermissions, generate_blob_sas

            # Get account info
            account_name = self.client.account_name
            credential = getattr(self.client, "credential", None)
            account_key = getattr(credential, "account_key", None)

            if isinstance(account_name, str) and isinstance(account_key, str) and account_key:
                # Generate SAS token
                sas_token = generate_blob_sas(
                    account_name=account_name,
                    container_name=self.container_name,
                    blob_name=blob_name,
                    account_key=account_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=datetime.now(UTC) + timedelta(seconds=expires_in),
                )

                return f"{blob_client.url}?{sas_token}"
            else:
                # If using managed identity, return direct URL (requires public access or additional auth)
                return str(blob_client.url)

        except AzureError as e:
            raise StorageError(
                message=f"Failed to generate report URL: {e!s}",
                storage_type="blob",
                original_error=e,
            ) from e

    async def cleanup_old_reports(self, days: int = 30) -> int:
        """Delete reports older than specified days from blob storage."""
        try:
            container = await self._container()

            cutoff_date = datetime.now(UTC) - timedelta(days=days)
            deleted_count = 0

            async for blob in container.list_blobs():
                if blob.last_modified.replace(tzinfo=UTC) < cutoff_date:
                    blob_client = container.get_blob_client(blob.name)
                    await blob_client.delete_blob()
                    deleted_count += 1

            return deleted_count

        except AzureError as e:
            raise StorageError(
                message=f"Failed to cleanup old reports: {e!s}",
                storage_type="blob",
                original_error=e,
            ) from e

    async def close(self) -> None:
        """Close the blob service client."""
        await self.client.close()
