"""Search command - find related prior research.

Provides semantic and keyword search across research reports.
Part of Context Discovery (6.1) feature.
"""

import asyncio

import click

from deepr.cli.colors import (
    console,
    print_error,
    print_header,
    print_info,
    print_key_value,
    print_success,
    print_warning,
    truncate_text,
)


@click.group()
def search():
    """Search and discover related research.

    Find prior research reports using semantic similarity
    and keyword matching.

    Examples:
        deepr search query "kubernetes deployment"
        deepr search index
        deepr search stats
    """
    pass


@search.command("query")
@click.argument("query")
@click.option("--top", "-n", default=5, help="Number of results to return")
@click.option("--threshold", "-t", default=0.7, help="Minimum similarity threshold (0-1)")
@click.option("--keyword-only", is_flag=True, help="Only use keyword search, skip embeddings")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def search_query(query: str, top: int, threshold: float, keyword_only: bool, json_output: bool):
    """Search for related research reports.

    Uses semantic similarity (embeddings) combined with keyword matching
    to find the most relevant prior research.

    Examples:
        deepr search query "kubernetes vs ECS"
        deepr search query "authentication patterns" --top 10
        deepr search query "AWS security" --threshold 0.8
    """
    asyncio.run(_search_query(query, top, threshold, keyword_only, json_output))


async def _search_query(query: str, top: int, threshold: float, keyword_only: bool, json_output: bool):
    """Execute search query."""
    from deepr.services.context_index import ContextIndex

    index = ContextIndex()

    # Check if index exists
    stats = index.get_stats()
    if stats["indexed_reports"] == 0:
        if json_output:
            console.print_json(data={"error": "No reports indexed", "results": []})
        else:
            print_warning("No reports indexed yet. Run 'deepr search index' first.")
        return

    # Perform search
    if not json_output:
        console.print(f"[dim]Searching {stats['indexed_reports']} reports...[/dim]")

    results = await index.search(
        query=query,
        top_k=top,
        threshold=threshold,
        include_keyword=not keyword_only or True,  # Always include keyword as fallback
    )

    if json_output:
        console.print_json(data={
            "query": query,
            "results": [r.to_dict() for r in results],
            "count": len(results),
        })
        return

    if not results:
        print_info("No matching reports found.")
        console.print("[dim]Try lowering the threshold with --threshold 0.5[/dim]")
        return

    print_header(f"Found {len(results)} Related Reports")

    for i, result in enumerate(results, 1):
        score_color = "green" if result.similarity >= 0.8 else "yellow" if result.similarity >= 0.7 else "dim"

        console.print(f"[bold]{i}.[/bold] [{score_color}]{result.similarity:.0%} match[/{score_color}]")
        console.print(f"   [cyan]{truncate_text(result.prompt, 70)}[/cyan]")
        if result.model:
            console.print(f"   [dim]Model: {result.model} | {result.created_at.strftime('%Y-%m-%d')}[/dim]")
        console.print(f"   [dim]Path: {result.report_path}[/dim]")
        console.print()

    console.print("[dim]View a report: cat <path>/report.md[/dim]")
    console.print("[dim]Use context: deepr research \"query\" --context <job-id>[/dim]")


@search.command("index")
@click.option("--force", "-f", is_flag=True, help="Re-index all reports")
def index_reports(force: bool):
    """Index reports for search.

    Scans the reports directory and indexes any new reports
    for semantic search. Run this periodically or after
    completing research jobs.

    Examples:
        deepr search index
        deepr search index --force
    """
    asyncio.run(_index_reports(force))


async def _index_reports(force: bool):
    """Execute report indexing."""
    from deepr.services.context_index import ContextIndex

    print_header("Indexing Reports")

    index = ContextIndex()

    if force:
        console.print("[dim]Force re-indexing all reports...[/dim]")
    else:
        console.print("[dim]Indexing new reports...[/dim]")

    try:
        count = await index.index_reports(force=force)

        if count > 0:
            print_success(f"Indexed {count} reports")
        else:
            print_info("No new reports to index")

        # Show stats
        stats = index.get_stats()
        console.print()
        print_key_value("Total indexed", str(stats["indexed_reports"]))
        print_key_value("Embeddings", str(stats["embedding_count"]))

    except Exception as e:
        print_error(f"Indexing failed: {e}")
        console.print("[dim]Make sure OPENAI_API_KEY is set for embedding generation[/dim]")


@search.command("stats")
def show_stats():
    """Show search index statistics.

    Display information about the indexed reports,
    embeddings, and storage.

    Example:
        deepr search stats
    """
    from deepr.services.context_index import ContextIndex

    print_header("Search Index Statistics")

    index = ContextIndex()
    stats = index.get_stats()

    print_key_value("Indexed Reports", str(stats["indexed_reports"]))
    print_key_value("Embeddings", str(stats["embedding_count"]))

    if stats["oldest_report"]:
        print_key_value("Date Range", f"{stats['oldest_report'][:10]} to {stats['newest_report'][:10]}")

    console.print()
    print_key_value("Database", stats["db_path"])
    print_key_value("Embeddings File", stats["embeddings_path"])


@search.command("clear")
@click.confirmation_option(prompt="Clear the entire search index?")
def clear_index():
    """Clear the search index.

    Removes all indexed reports and embeddings.
    Use --force to skip confirmation.

    Example:
        deepr search clear
    """
    from deepr.services.context_index import ContextIndex

    index = ContextIndex()
    index.clear()

    print_success("Search index cleared")
