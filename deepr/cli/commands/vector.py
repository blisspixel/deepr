"""Vector store commands - manage persistent vector stores for file uploads."""

import click
from typing import Optional
from deepr.branding import print_section_header, CHECK, CROSS


@click.group()
def vector():
    """Manage persistent vector stores for file uploads."""
    pass


@vector.command()
@click.option("--name", "-n", required=True, help="Name for the vector store")
@click.option("--files", "-f", multiple=True, type=click.Path(exists=True), required=True,
              help="Files to upload and index")
def create(name: str, files: tuple):
    """
    Create a persistent vector store from files.

    Vector stores enable semantic search over uploaded documents.
    Once created, they can be reused across multiple research jobs.

    Example:
        deepr vector create --name "company-docs" --files docs/*.pdf
        deepr research submit "Query about X" --vector-store company-docs --yes
    """
    print_section_header(f"Create Vector Store: {name}")

    try:
        import asyncio
        import os
        from deepr.config import load_config
        from deepr.providers.openai_provider import OpenAIProvider

        if not files:
            click.echo(f"\n{CROSS} No files specified. Use --files to add documents.", err=True)
            raise click.Abort()

        config = load_config()
        provider = OpenAIProvider(api_key=config["api_key"])

        async def create_store():
            # Upload files
            click.echo(f"\nUploading {len(files)} file(s)...")
            file_ids = []

            for file_path in files:
                basename = os.path.basename(file_path)
                click.echo(f"   Uploading {basename}...")
                file_id = await provider.upload_document(file_path, purpose="assistants")
                file_ids.append(file_id)
                click.echo(f"   {CHECK} Uploaded (ID: {file_id[:8]}...)")

            # Create vector store
            click.echo(f"\n{CHECK} Creating vector store '{name}'...")
            vector_store = await provider.create_vector_store(name, file_ids)

            # Wait for indexing
            click.echo(f"\n   Indexing files (this may take a minute)...")
            success = await provider.wait_for_vector_store(vector_store.id, timeout=900)

            if success:
                click.echo(f"\n{CHECK} Vector store created successfully!")
                click.echo(f"\nVector Store ID: {vector_store.id}")
                click.echo(f"Name: {name}")
                click.echo(f"Files: {len(file_ids)}")
                click.echo(f"\nUsage:")
                click.echo(f'  deepr research submit "prompt" --vector-store {vector_store.id} --yes')
                return vector_store.id
            else:
                click.echo(f"\n{CROSS} Indexing timed out", err=True)
                raise click.Abort()

        vector_store_id = asyncio.run(create_store())

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@vector.command()
@click.option("--limit", "-l", default=20, help="Maximum number to list")
def list(limit: int):
    """
    List all vector stores.

    Shows all persistent vector stores available for research.

    Example:
        deepr vector list
        deepr vector list --limit 50
    """
    print_section_header("Vector Stores")

    try:
        import asyncio
        from deepr.config import load_config
        from deepr.providers.openai_provider import OpenAIProvider

        config = load_config()
        provider = OpenAIProvider(api_key=config["api_key"])

        async def list_stores():
            stores = await provider.list_vector_stores(limit=limit)
            return stores

        stores = asyncio.run(list_stores())

        if not stores:
            click.echo(f"\nNo vector stores found.")
            click.echo(f"\nCreate one with: deepr vector create --name <name> --files <files>")
            return

        click.echo(f"\nFound {len(stores)} vector store(s):\n")

        for store in stores:
            file_count = len(store.file_ids)
            click.echo(f"  {store.name}")
            click.echo(f"    ID: {store.id}")
            click.echo(f"    Files: {file_count}")
            click.echo()

        click.echo(f"Usage:")
        click.echo(f'  deepr research submit "prompt" --vector-store <id> --yes')

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@vector.command()
@click.argument("vector_store_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete(vector_store_id: str, yes: bool):
    """
    Delete a vector store.

    Permanently removes the vector store and its indexed data.
    This does not delete the original files.

    Example:
        deepr vector delete vs_abc123
        deepr vector delete vs_abc123 --yes
    """
    print_section_header(f"Delete Vector Store")

    try:
        import asyncio
        from deepr.config import load_config
        from deepr.providers.openai_provider import OpenAIProvider

        config = load_config()
        provider = OpenAIProvider(api_key=config["api_key"])

        # Confirmation
        if not yes:
            click.echo(f"\nVector Store ID: {vector_store_id}")
            click.echo(f"\nThis will permanently delete the vector store.")
            click.echo(f"Original files will not be affected.")
            if not click.confirm(f"\nDelete vector store?"):
                click.echo(f"\n{CROSS} Cancelled")
                return

        async def delete_store():
            success = await provider.delete_vector_store(vector_store_id)
            return success

        success = asyncio.run(delete_store())

        if success:
            click.echo(f"\n{CHECK} Vector store deleted: {vector_store_id}")
        else:
            click.echo(f"\n{CROSS} Failed to delete vector store", err=True)
            raise click.Abort()

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@vector.command()
@click.option("--pattern", "-p", help="Delete stores matching name pattern (e.g., 'research-*')")
@click.option("--all", "-a", is_flag=True, help="Delete all vector stores")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
def cleanup(pattern: str, all: bool, yes: bool, dry_run: bool):
    """
    Clean up vector stores in bulk.

    Examples:
        deepr vector cleanup --pattern "research-*" --yes
        deepr vector cleanup --all --dry-run
        deepr vector cleanup --pattern "test*"
    """
    print_section_header("Vector Store Cleanup")

    try:
        import asyncio
        import fnmatch
        from deepr.config import load_config
        from deepr.providers.openai_provider import OpenAIProvider

        config = load_config()
        provider = OpenAIProvider(api_key=config["api_key"])

        async def cleanup_stores():
            stores = await provider.list_vector_stores(limit=100)

            if not stores:
                click.echo("\nNo vector stores found.")
                return 0

            # Filter stores based on criteria
            to_delete = []

            if all:
                click.echo("\n[!] --all flag specified: Will delete ALL vector stores")
                to_delete = stores
            elif pattern:
                click.echo(f"\nFinding stores matching pattern: {pattern}")
                for store in stores:
                    if store.name and fnmatch.fnmatch(store.name, pattern):
                        to_delete.append(store)
            else:
                click.echo("\n[!] No filter specified. Use --pattern or --all")
                click.echo("Example: deepr vector cleanup --pattern 'research-*'")
                return 0

            if not to_delete:
                click.echo("\nNo stores match criteria.")
                return 0

            # Show what will be deleted
            click.echo(f"\nVector stores to delete: {len(to_delete)}")
            for store in to_delete:
                click.echo(f"  - {store.name or 'Unnamed'} ({store.id[:25]}...) - {len(store.file_ids)} files")

            if dry_run:
                click.echo(f"\n[DRY RUN] Would delete {len(to_delete)} store(s)")
                return 0

            # Confirm deletion
            if not yes:
                click.echo(f"\n[!] This will permanently delete {len(to_delete)} vector store(s)")
                if not click.confirm("Continue?"):
                    click.echo("\nCancelled")
                    return 0

            # Delete stores
            deleted = 0
            failed = 0

            click.echo(f"\nDeleting...")
            for store in to_delete:
                try:
                    success = await provider.delete_vector_store(store.id)
                    if success:
                        click.echo(f"  {CHECK} {store.name or 'Unnamed'}")
                        deleted += 1
                    else:
                        click.echo(f"  {CROSS} Failed: {store.name or 'Unnamed'}")
                        failed += 1
                except Exception as e:
                    click.echo(f"  {CROSS} Error: {store.name or 'Unnamed'} - {e}")
                    failed += 1

            click.echo(f"\nDeleted: {deleted}")
            if failed:
                click.echo(f"Failed: {failed}")

            return deleted

        deleted = asyncio.run(cleanup_stores())

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@vector.command()
@click.argument("vector_store_id")
def info(vector_store_id: str):
    """
    Show detailed information about a vector store.

    Displays metadata and file information for a vector store.

    Example:
        deepr vector info vs_abc123
    """
    print_section_header(f"Vector Store Info")

    try:
        import asyncio
        from deepr.config import load_config
        from deepr.providers.openai_provider import OpenAIProvider

        config = load_config()
        provider = OpenAIProvider(api_key=config["api_key"])

        async def get_info():
            # List all stores and find the matching one
            stores = await provider.list_vector_stores(limit=100)

            for store in stores:
                if store.id == vector_store_id or store.name == vector_store_id:
                    return store

            return None

        store = asyncio.run(get_info())

        if not store:
            click.echo(f"\n{CROSS} Vector store not found: {vector_store_id}", err=True)
            raise click.Abort()

        click.echo(f"\nName: {store.name}")
        click.echo(f"ID: {store.id}")
        click.echo(f"Files: {len(store.file_ids)}")

        if store.file_ids:
            click.echo(f"\nFile IDs:")
            for file_id in store.file_ids:
                click.echo(f"  - {file_id}")

        click.echo(f"\nUsage:")
        click.echo(f'  deepr research submit "prompt" --vector-store {store.id} --yes')

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()
