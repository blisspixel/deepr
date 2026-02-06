"""Document management and vector store operations."""

from pathlib import Path

from ..providers.base import DeepResearchProvider, VectorStore


class DocumentManager:
    """Manages document uploads and vector store operations."""

    async def upload_documents(self, file_paths: list[str], provider: DeepResearchProvider) -> list[str]:
        """
        Upload multiple documents to the provider.

        Args:
            file_paths: List of paths to document files
            provider: Provider instance to use for upload

        Returns:
            List of uploaded file IDs

        Raises:
            FileNotFoundError: If any file doesn't exist
            Exception: If upload fails
        """
        file_ids = []

        for path_str in file_paths:
            path = Path(path_str)

            # Validate file exists
            if not path.exists():
                raise FileNotFoundError(f"Document not found: {path}")

            # Upload to provider
            file_id = await provider.upload_document(str(path))
            file_ids.append(file_id)

        return file_ids

    async def create_vector_store(self, name: str, file_ids: list[str], provider: DeepResearchProvider) -> VectorStore:
        """
        Create a vector store with the given files.

        Args:
            name: Name for the vector store
            file_ids: List of file IDs to include
            provider: Provider instance

        Returns:
            VectorStore information

        Raises:
            Exception: If creation fails
        """
        # Create vector store
        vector_store = await provider.create_vector_store(name, file_ids)

        # Wait for ingestion to complete
        await provider.wait_for_vector_store(vector_store.id)

        return vector_store

    @staticmethod
    def validate_file_type(file_path: str) -> bool:
        """
        Check if file type is supported for document upload.

        Args:
            file_path: Path to the file

        Returns:
            True if file type is supported
        """
        supported_extensions = {
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".xml",
        }

        path = Path(file_path)
        return path.suffix.lower() in supported_extensions

    @staticmethod
    def get_file_size(file_path: str) -> int:
        """
        Get file size in bytes.

        Args:
            file_path: Path to the file

        Returns:
            File size in bytes
        """
        return Path(file_path).stat().st_size
