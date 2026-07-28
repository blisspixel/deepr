"""Search command - find related prior research.

Provides semantic and keyword search across research reports.
Part of Context Discovery (6.1) feature.
"""

from math import isfinite

import click

from deepr.cli.async_runner import run_async_command
from deepr.cli.colors import (
    console,
    print_header,
    print_info,
    print_key_value,
    print_success,
    print_warning,
    truncate_text,
)

_SEMANTIC_BACKEND = "openai"


def _require_semantic_consent(
    *,
    semantic_backend: str | None,
    max_total_cost: float | None,
    confirm_metered_cost: bool,
    keyword_only: bool = False,
) -> float | None:
    """Return the explicit aggregate ceiling for a paid semantic request."""
    if semantic_backend is None:
        if max_total_cost is not None or confirm_metered_cost:
            raise click.UsageError(
                "--max-total-cost and --confirm-metered-cost require an explicit --semantic-backend."
            )
        return None
    if keyword_only:
        raise click.UsageError("--keyword-only cannot be combined with --semantic-backend.")
    if semantic_backend != _SEMANTIC_BACKEND:
        raise click.UsageError(f"Unsupported semantic backend: {semantic_backend}")
    if (
        max_total_cost is None
        or isinstance(max_total_cost, bool)
        or not isinstance(max_total_cost, (int, float))
        or not isfinite(float(max_total_cost))
        or float(max_total_cost) <= 0
    ):
        raise click.UsageError("Paid semantic search requires an explicit finite positive --max-total-cost ceiling.")
    if not confirm_metered_cost:
        raise click.UsageError(
            "Paid semantic search requires --confirm-metered-cost; the ceiling is not permission to spend."
        )
    return float(max_total_cost)


def _require_query_envelope(query: str, ceiling: float) -> None:
    """Prove the single semantic-query embedding fits the aggregate ceiling."""
    from deepr.services.metered_envelope import bounded_embedding_envelope

    envelope = bounded_embedding_envelope(
        model="text-embedding-3-small",
        inputs=(query[:8000],),
    )
    if envelope.cost_usd > ceiling + 1e-12:
        raise click.UsageError(
            f"Semantic query requires up to ${envelope.cost_usd:.6f}, above --max-total-cost ${ceiling:.6f}."
        )


class SearchGroup(click.Group):
    """Route bare search terms to the query command."""

    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            if args and not args[0].startswith("-"):
                return "query", self.commands["query"], args
            raise


@click.group(cls=SearchGroup)
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
@click.option("--keyword-only", is_flag=True, help="Use only local keyword search")
@click.option(
    "--semantic-backend",
    "--backend",
    type=click.Choice([_SEMANTIC_BACKEND]),
    default=None,
    help="Explicit paid embedding backend. Omit for local keyword search.",
)
@click.option(
    "--max-total-cost",
    "--max-cost",
    type=float,
    default=None,
    help="Finite aggregate USD ceiling required with --semantic-backend.",
)
@click.option(
    "--confirm-metered-cost",
    is_flag=True,
    help="Confirm paid semantic embedding calls up to --max-total-cost.",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def search_query(
    query: str,
    top: int,
    threshold: float,
    keyword_only: bool,
    semantic_backend: str | None,
    max_total_cost: float | None,
    confirm_metered_cost: bool,
    json_output: bool,
):
    """Search for related research reports.

    Uses local keyword matching by default. Semantic similarity is an explicit
    paid path requiring a backend, aggregate ceiling, and cost confirmation.

    Examples:
        deepr search query "kubernetes vs ECS"
        deepr search query "authentication patterns" --top 10
        deepr search query "AWS security" --threshold 0.8
    """
    ceiling = _require_semantic_consent(
        semantic_backend=semantic_backend,
        max_total_cost=max_total_cost,
        confirm_metered_cost=confirm_metered_cost,
        keyword_only=keyword_only,
    )
    if ceiling is not None:
        _require_query_envelope(query, ceiling)
    run_async_command(
        _search_query(
            query,
            top,
            threshold,
            keyword_only,
            json_output,
            semantic_backend=semantic_backend,
            max_total_cost=ceiling,
        )
    )


async def _search_query(
    query: str,
    top: int,
    threshold: float,
    keyword_only: bool,
    json_output: bool,
    *,
    semantic_backend: str | None = None,
    max_total_cost: float | None = None,
):
    """Execute search query."""
    from deepr.services.context_index import ContextIndex, PaidSemanticOperationError

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

    try:
        results = await index.search(
            query=query,
            top_k=top,
            threshold=threshold,
            include_keyword=True,
            include_semantic=semantic_backend is not None and not keyword_only and max_total_cost is not None,
            max_total_cost_usd=max_total_cost,
        )
    except PaidSemanticOperationError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        console.print_json(
            data={
                "query": query,
                "results": [r.to_dict() for r in results],
                "count": len(results),
            }
        )
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
    console.print('[dim]Use context: deepr research "query" --context <job-id>[/dim]')


@search.command("index")
@click.option("--force", "-f", is_flag=True, help="Re-index all reports")
@click.option(
    "--semantic-backend",
    "--backend",
    type=click.Choice([_SEMANTIC_BACKEND]),
    default=None,
    help="Explicit paid embedding backend. Omit for local keyword indexing.",
)
@click.option(
    "--max-total-cost",
    "--max-cost",
    type=float,
    default=None,
    help="Finite aggregate USD ceiling required with --semantic-backend.",
)
@click.option(
    "--confirm-metered-cost",
    is_flag=True,
    help="Confirm paid report embedding calls up to --max-total-cost.",
)
def index_reports(
    force: bool,
    semantic_backend: str | None,
    max_total_cost: float | None,
    confirm_metered_cost: bool,
):
    """Index reports for search.

    Scans the reports directory and builds the local keyword index. Paid
    semantic embeddings require explicit metered authorization.

    Examples:
        deepr search index
        deepr search index --force
    """
    ceiling = _require_semantic_consent(
        semantic_backend=semantic_backend,
        max_total_cost=max_total_cost,
        confirm_metered_cost=confirm_metered_cost,
    )
    run_async_command(
        _index_reports(
            force,
            semantic_backend=semantic_backend,
            max_total_cost=ceiling,
        )
    )


async def _index_reports(
    force: bool,
    *,
    semantic_backend: str | None = None,
    max_total_cost: float | None = None,
):
    """Execute report indexing."""
    from deepr.services.context_index import ContextIndex, PaidSemanticOperationError

    print_header("Indexing Reports")

    index = ContextIndex()

    if force:
        console.print("[dim]Force re-indexing all reports...[/dim]")
    else:
        console.print("[dim]Indexing new reports...[/dim]")

    try:
        count = await index.index_reports(
            force=force,
            include_semantic=semantic_backend is not None,
            max_total_cost_usd=max_total_cost,
        )

        if count > 0:
            print_success(f"Indexed {count} reports")
        else:
            print_info("No new reports to index")

        # Show stats
        stats = index.get_stats()
        console.print()
        print_key_value("Total indexed", str(stats["indexed_reports"]))
        print_key_value("Embeddings", str(stats["embedding_count"]))

    except PaidSemanticOperationError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException(f"Indexing failed: {exc}") from exc


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
