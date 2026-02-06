"""Azure Blob Storage implementation."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient, ContainerClient

from .base import ReportMetadata, StorageBackend, StorageError


class AzureBlobStorage(StorageBackend):
    """Azure Blob Storage implementation of storage backend."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        account_url: Optional[str] = None,
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

        self.container_client: Optional[ContainerClient] = None

    async def _ensure_container(self):
        """Ensure container exists, create if necessary."""
        if self.container_client is None:
            self.container_client = self.client.get_container_client(self.container_name)
            try:
                await self.container_client.get_container_properties()
            except ResourceNotFoundError:
                # Container doesn't exist, create it
                await self.container_client.create_container()

    def _get_blob_name(self, job_id: str, filename: str) -> str:
        """Generate blob name from job_id and filename."""
        return f"{job_id}/{filename}"

    async def save_report(
        self,
        job_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReportMetadata:
        """Save report to Azure Blob Storage."""
        try:
            await self._ensure_container()

            blob_name = self._get_blob_name(job_id, filename)
            blob_client = self.container_client.get_blob_client(blob_name)

            # Prepare blob metadata
            blob_metadata = metadata or {}
            blob_metadata["job_id"] = job_id
            blob_metadata["filename"] = filename

            # Upload blob
            await blob_client.upload_blob(content, content_type=content_type, metadata=blob_metadata, overwrite=True)

            # Get blob properties
            props = await blob_client.get_blob_properties()

            # Determine format from filename
            format_ext = filename.split(".")[-1] if "." in filename else ""

            return ReportMetadata(
                job_id=job_id,
                filename=filename,
                format=format_ext,
                size_bytes=props.size,
                created_at=props.last_modified.replace(tzinfo=timezone.utc),
                url=blob_client.url,
                content_type=content_type,
            )

        except AzureError as e:
            raise StorageError(
                message=f"Failed to save report to blob storage: {str(e)}",
                storage_type="blob",
                original_error=e,
            )

    async def get_report(self, job_id: str, filename: str) -> bytes:
        """Retrieve report from Azure Blob Storage."""
        try:
            await self._ensure_container()

            blob_name = self._get_blob_name(job_id, filename)
            blob_client = self.container_client.get_blob_client(blob_name)

            # Download blob
            stream = await blob_client.download_blob()
            content = await stream.readall()

            return content

        except ResourceNotFoundError:
            raise StorageError(
                message=f"Report not found: {job_id}/{filename}",
                storage_type="blob",
                original_error=None,
            )
        except AzureError as e:
            raise StorageError(
                message=f"Failed to retrieve report from blob storage: {str(e)}",
                storage_type="blob",
                original_error=e,
            )

    async def list_reports(self, job_id: Optional[str] = None) -> List[ReportMetadata]:
        """List reports in Azure Blob Storage."""
        try:
            await self._ensure_container()

            reports = []
            prefix = f"{job_id}/" if job_id else ""

            async for blob in self.container_client.list_blobs(name_starts_with=prefix):
                # Parse job_id and filename from blob name
                parts = blob.name.split("/", 1)
                if len(parts) == 2:
                    blob_job_id, blob_filename = parts
                else:
                    continue

                # Determine format
                format_ext = blob_filename.split(".")[-1] if "." in blob_filename else ""

                reports.append(
                    ReportMetadata(
                        job_id=blob_job_id,
                        filename=blob_filename,
                        format=format_ext,
                        size_bytes=blob.size,
                        created_at=blob.last_modified.replace(tzinfo=timezone.utc),
                        url=f"{self.container_client.url}/{blob.name}",
                        content_type=self.get_content_type(blob_filename),
                    )
                )

            return reports

        except AzureError as e:
            raise StorageError(
                message=f"Failed to list reports in blob storage: {str(e)}",
                storage_type="blob",
                original_error=e,
            )

    async def delete_report(self, job_id: str, filename: Optional[str] = None) -> bool:
        """Delete report(s) from Azure Blob Storage."""
        try:
            await self._ensure_container()

            if filename:
                # Delete specific blob
                blob_name = self._get_blob_name(job_id, filename)
                blob_client = self.container_client.get_blob_client(blob_name)
                await blob_client.delete_blob()
                return True
            else:
                # Delete all blobs for this job
                deleted = False
                prefix = f"{job_id}/"
                async for blob in self.container_client.list_blobs(name_starts_with=prefix):
                    blob_client = self.container_client.get_blob_client(blob.name)
                    await blob_client.delete_blob()
                    deleted = True
                return deleted

        except ResourceNotFoundError:
            return False
        except AzureError as e:
            raise StorageError(
                message=f"Failed to delete report from blob storage: {str(e)}",
                storage_type="blob",
                original_error=e,
            )

    async def report_exists(self, job_id: str, filename: str) -> bool:
        """Check if report exists in Azure Blob Storage."""
        try:
            await self._ensure_container()

            blob_name = self._get_blob_name(job_id, filename)
            blob_client = self.container_client.get_blob_client(blob_name)

            await blob_client.get_blob_properties()
            return True

        except ResourceNotFoundError:
            return False
        except AzureError:
            return False

    async def get_report_url(self, job_id: str, filename: str, expires_in: int = 3600) -> str:
        """Get signed URL for report access."""
        try:
            await self._ensure_container()

            blob_name = self._get_blob_name(job_id, filename)
            blob_client = self.container_client.get_blob_client(blob_name)

            # Generate SAS token for time-limited access
            from azure.storage.blob import BlobSasPermissions, generate_blob_sas

            # Get account info
            account_name = self.client.account_name
            account_key = self.client.credential.account_key if hasattr(self.client.credential, "account_key") else None

            if account_key:
                # Generate SAS token
                sas_token = generate_blob_sas(
                    account_name=account_name,
                    container_name=self.container_name,
                    blob_name=blob_name,
                    account_key=account_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                )

                return f"{blob_client.url}?{sas_token}"
            else:
                # If using managed identity, return direct URL (requires public access or additional auth)
                return blob_client.url

        except AzureError as e:
            raise StorageError(
                message=f"Failed to generate report URL: {str(e)}",
                storage_type="blob",
                original_error=e,
            )

    async def cleanup_old_reports(self, days: int = 30) -> int:
        """Delete reports older than specified days from blob storage."""
        try:
            await self._ensure_container()

            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            deleted_count = 0

            async for blob in self.container_client.list_blobs():
                if blob.last_modified.replace(tzinfo=timezone.utc) < cutoff_date:
                    blob_client = self.container_client.get_blob_client(blob.name)
                    await blob_client.delete_blob()
                    deleted_count += 1

            return deleted_count

        except AzureError as e:
            raise StorageError(
                message=f"Failed to cleanup old reports: {str(e)}",
                storage_type="blob",
                original_error=e,
            )

    async def close(self):
        """Close the blob service client."""
        await self.client.close()
