"""File handling utilities for CLI commands.

Extracts file pattern resolution, upload, and vector store creation logic.
Reduces complexity in run.py by centralizing file operations.

Requirements: 6.3 - Extract file handling logic
"""

import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from deepr.cli.output import OutputFormatter, OutputMode


@dataclass
class FileUploadResult:
    """Result of file upload operation."""
    resolved_files: List[Path]
    uploaded_ids: List[str]
    vector_store_id: Optional[str]
    errors: List[str]
    
    @property
    def success(self) -> bool:
        """Check if any files were uploaded successfully."""
        return len(self.uploaded_ids) > 0
    
    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0


def resolve_file_patterns(
    patterns: tuple,
    formatter: Optional[OutputFormatter] = None
) -> Tuple[List[Path], List[str]]:
    """Resolve file patterns to actual file paths.
    
    Handles glob patterns, Windows paths, and spaces in filenames.
    
    Args:
        patterns: Tuple of file patterns/paths
        formatter: Optional formatter for progress messages
        
    Returns:
        Tuple of (resolved_files, errors)
    """
    from deepr.utils.paths import resolve_file_path, resolve_glob_pattern
    
    resolved_files = []
    errors = []
    
    for file_pattern in patterns:
        try:
            # Check if it's a glob pattern
            if '*' in file_pattern or '?' in file_pattern:
                matched = resolve_glob_pattern(file_pattern, must_match=True)
                resolved_files.extend(matched)
                if formatter:
                    formatter.progress(f"Pattern '{file_pattern}' matched {len(matched)} file(s)")
            else:
                # Single file
                resolved = resolve_file_path(file_pattern, must_exist=True)
                resolved_files.append(resolved)
        except FileNotFoundError as e:
            errors.append(str(e))
    
    return resolved_files, errors


async def upload_files(
    provider_instance,
    files: List[Path],
    formatter: Optional[OutputFormatter] = None
) -> Tuple[List[str], List[str]]:
    """Upload files to provider.
    
    Args:
        provider_instance: Initialized provider
        files: List of file paths to upload
        formatter: Optional formatter for progress messages
        
    Returns:
        Tuple of (uploaded_file_ids, errors)
    """
    from deepr.utils.paths import normalize_path_for_display
    
    uploaded_ids = []
    errors = []
    
    for file_path in files:
        display_name = file_path.name
        
        if formatter:
            formatter.progress(f"Uploading: {display_name}")
        
        try:
            file_id = await provider_instance.upload_document(str(file_path))
            uploaded_ids.append(file_id)
            if formatter:
                formatter.progress(f"Uploaded: {display_name}")
        except Exception as e:
            errors.append(f"Failed to upload {display_name}: {e}")
    
    return uploaded_ids, errors


async def create_vector_store_for_files(
    provider_instance,
    file_ids: List[str],
    formatter: Optional[OutputFormatter] = None,
    timeout: int = 300
) -> Tuple[Optional[str], List[str]]:
    """Create vector store and wait for file processing.
    
    Args:
        provider_instance: Initialized provider
        file_ids: List of uploaded file IDs
        formatter: Optional formatter for progress messages
        timeout: Timeout in seconds for file processing
        
    Returns:
        Tuple of (vector_store_id, errors)
    """
    errors = []
    
    if formatter:
        formatter.progress("Creating vector store...")
    
    try:
        vs = await provider_instance.create_vector_store(
            name=f"research-{uuid.uuid4().hex[:8]}",
            file_ids=file_ids
        )
        vector_store_id = vs.id
        
        if formatter:
            formatter.progress(f"Vector store created: {vs.id[:20]}...")
            formatter.progress("Waiting for file processing...")
        
        # Wait for ingestion
        ready = await provider_instance.wait_for_vector_store(
            vs.id,
            timeout=timeout,
            poll_interval=2.0
        )
        
        if ready:
            if formatter:
                formatter.progress("Files ready for research")
        else:
            errors.append("Files still processing (continuing anyway)")
        
        return vector_store_id, errors
        
    except Exception as e:
        errors.append(f"Vector store creation failed: {e}")
        return None, errors


async def handle_file_uploads(
    provider: str,
    upload_patterns: tuple,
    formatter: Optional[OutputFormatter] = None,
    config: Optional[dict] = None
) -> FileUploadResult:
    """Handle complete file upload workflow.
    
    Resolves patterns, uploads files, and creates vector store if needed.
    
    Args:
        provider: Provider name
        upload_patterns: Tuple of file patterns
        formatter: Optional formatter for progress messages
        config: Optional config dict
        
    Returns:
        FileUploadResult with all upload information
    """
    from deepr.cli.commands.provider_factory import (
        create_provider_instance,
        supports_vector_stores
    )
    
    result = FileUploadResult(
        resolved_files=[],
        uploaded_ids=[],
        vector_store_id=None,
        errors=[]
    )
    
    if not upload_patterns:
        return result
    
    if formatter:
        formatter.progress("Uploading files...")
    
    # Resolve file patterns
    resolved_files, resolve_errors = resolve_file_patterns(upload_patterns, formatter)
    result.resolved_files = resolved_files
    result.errors.extend(resolve_errors)
    
    if not resolved_files:
        result.errors.append("No files to upload")
        return result
    
    if formatter:
        formatter.progress(f"Found {len(resolved_files)} file(s) to upload")
    
    # Create provider instance
    try:
        provider_instance = create_provider_instance(provider, config)
    except Exception as e:
        result.errors.append(f"Failed to create provider: {e}")
        return result
    
    # Upload files
    uploaded_ids, upload_errors = await upload_files(
        provider_instance, resolved_files, formatter
    )
    result.uploaded_ids = uploaded_ids
    result.errors.extend(upload_errors)
    
    if not uploaded_ids:
        result.errors.append("No files uploaded successfully")
        return result
    
    # Create vector store for OpenAI/Azure
    if supports_vector_stores(provider):
        vector_store_id, vs_errors = await create_vector_store_for_files(
            provider_instance, uploaded_ids, formatter
        )
        result.vector_store_id = vector_store_id
        result.errors.extend(vs_errors)
    else:
        # For other providers, files are referenced directly
        if formatter:
            formatter.progress(f"{len(uploaded_ids)} files ready for research")
    
    return result
