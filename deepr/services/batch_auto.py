"""Batch executor for auto-mode research queries.

Processes multiple queries cost-effectively by routing each to the
optimal model based on complexity.

Supported file formats:
- .txt: Simple format, one query per line (# for comments)
- .json: Advanced format with per-query options

Example .txt:
    # Simple queries
    What is the capital of France?
    Analyze the AI market in 2025
    Compare AWS vs Azure

Example .json:
    {
      "queries": [
        {"query": "What is Python?", "priority": 5},
        {"query": "Analyze Tesla", "cost_limit": 1.0},
        {"query": "Compare AWS vs Azure", "force_model": "o3-deep-research"}
      ],
      "defaults": {"prefer_cost": true}
    }
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from deepr.routing.auto_mode import AutoModeDecision, AutoModeRouter, BatchRoutingResult


@dataclass
class BatchQueryItem:
    """A single query item in a batch.

    Attributes:
        query: The research query text
        priority: Query priority (1-10, higher = more priority)
        cost_limit: Maximum cost for this query
        force_model: Override auto-routing with specific model
        force_provider: Override auto-routing with specific provider
        metadata: Additional metadata for tracking
    """

    query: str
    priority: int = 5
    cost_limit: Optional[float] = None
    force_model: Optional[str] = None
    force_provider: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchQueryResult:
    """Result for a single query in the batch.

    Attributes:
        query: Original query
        decision: Routing decision that was used
        job_id: Job ID if executed
        success: Whether execution succeeded
        error: Error message if failed
        cost_actual: Actual cost incurred
        report_path: Path to result report
    """

    query: str
    decision: AutoModeDecision
    job_id: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    cost_actual: float = 0.0
    report_path: Optional[str] = None


@dataclass
class BatchResult:
    """Result of batch execution.

    Attributes:
        batch_id: Unique batch identifier
        started_at: When batch started
        completed_at: When batch completed
        results: Results for each query
        total_cost_estimated: Estimated total cost
        total_cost_actual: Actual total cost
        success_count: Number of successful queries
        failure_count: Number of failed queries
    """

    batch_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    results: List[BatchQueryResult] = field(default_factory=list)
    total_cost_estimated: float = 0.0
    total_cost_actual: float = 0.0
    success_count: int = 0
    failure_count: int = 0


def parse_batch_file(file_path: str) -> tuple[List[BatchQueryItem], Dict[str, Any]]:
    """Parse a batch file (.txt or .json) into query items.

    Args:
        file_path: Path to batch file

    Returns:
        Tuple of (list of BatchQueryItem, defaults dict)

    Raises:
        ValueError: If file format is invalid
    """
    path = Path(file_path)

    if not path.exists():
        raise ValueError(f"Batch file not found: {file_path}")

    suffix = path.suffix.lower()

    if suffix == ".txt":
        return _parse_txt_file(path), {}
    elif suffix == ".json":
        return _parse_json_file(path)
    else:
        raise ValueError(f"Unsupported batch file format: {suffix}. Use .txt or .json")


def _parse_txt_file(path: Path) -> List[BatchQueryItem]:
    """Parse simple text file format (one query per line)."""
    items = []

    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            items.append(
                BatchQueryItem(
                    query=line,
                    metadata={"source_line": line_num},
                )
            )

    return items


def _parse_json_file(path: Path) -> tuple[List[BatchQueryItem], Dict[str, Any]]:
    """Parse JSON file format with per-query options."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    defaults = data.get("defaults", {})
    queries_data = data.get("queries", [])

    if not queries_data:
        raise ValueError("JSON batch file must have 'queries' array")

    items = []
    for idx, item_data in enumerate(queries_data):
        if isinstance(item_data, str):
            # Simple string query
            items.append(BatchQueryItem(query=item_data))
        elif isinstance(item_data, dict):
            # Full query object
            query = item_data.get("query")
            if not query:
                raise ValueError(f"Query at index {idx} missing 'query' field")

            items.append(
                BatchQueryItem(
                    query=query,
                    priority=item_data.get("priority", defaults.get("priority", 5)),
                    cost_limit=item_data.get("cost_limit", defaults.get("cost_limit")),
                    force_model=item_data.get("force_model"),
                    force_provider=item_data.get("force_provider"),
                    metadata=item_data.get("metadata", {}),
                )
            )
        else:
            raise ValueError(f"Invalid query format at index {idx}")

    return items, defaults


class AutoBatchExecutor:
    """Executes batches of queries with auto-mode routing.

    Example:
        executor = AutoBatchExecutor()

        # Dry run to preview routing
        routing = executor.preview_batch("queries.txt")
        print(f"Estimated cost: ${routing.total_cost_estimate:.2f}")

        # Execute batch
        result = await executor.execute_batch(
            queries="queries.txt",
            campaign_id="my-batch",
            progress_callback=lambda msg: print(msg),
        )
    """

    def __init__(
        self,
        router: Optional[AutoModeRouter] = None,
        max_concurrent: int = 5,
    ):
        """Initialize batch executor.

        Args:
            router: Optional AutoModeRouter instance
            max_concurrent: Maximum concurrent queries
        """
        self._router = router or AutoModeRouter()
        self._max_concurrent = max_concurrent

    def preview_batch(
        self,
        file_path: str,
        budget_total: Optional[float] = None,
        prefer_cost: bool = False,
    ) -> BatchRoutingResult:
        """Preview routing decisions without executing (dry run).

        Args:
            file_path: Path to batch file
            budget_total: Optional total budget constraint
            prefer_cost: If True, prefer cheaper options

        Returns:
            BatchRoutingResult with routing decisions and cost estimates
        """
        items, defaults = parse_batch_file(file_path)
        queries = [item.query for item in items]

        # Apply defaults
        if defaults.get("prefer_cost"):
            prefer_cost = True

        return self._router.route_batch(
            queries=queries,
            budget_total=budget_total,
            prefer_cost=prefer_cost,
        )

    async def execute_batch(
        self,
        file_path: str,
        campaign_id: Optional[str] = None,
        budget_total: Optional[float] = None,
        prefer_cost: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
        dry_run: bool = False,
    ) -> BatchResult:
        """Execute a batch of queries with auto-mode routing.

        Args:
            file_path: Path to batch file (.txt or .json)
            campaign_id: Optional campaign identifier
            budget_total: Optional total budget constraint
            prefer_cost: If True, prefer cheaper options
            progress_callback: Optional callback for progress updates
            dry_run: If True, only preview routing without executing

        Returns:
            BatchResult with execution results
        """
        batch_id = campaign_id or f"batch-{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc)

        # Parse batch file
        items, defaults = parse_batch_file(file_path)

        if defaults.get("prefer_cost"):
            prefer_cost = True

        # Get routing decisions
        queries = [item.query for item in items]
        routing = self._router.route_batch(
            queries=queries,
            budget_total=budget_total,
            prefer_cost=prefer_cost,
        )

        if progress_callback:
            progress_callback(f"Routed {len(queries)} queries, estimated cost: ${routing.total_cost_estimate:.2f}")

        # For dry run, return early with routing info
        if dry_run:
            results = [
                BatchQueryResult(
                    query=item.query,
                    decision=decision,
                )
                for item, decision in zip(items, routing.decisions)
            ]

            return BatchResult(
                batch_id=batch_id,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                results=results,
                total_cost_estimated=routing.total_cost_estimate,
                total_cost_actual=0.0,
                success_count=0,
                failure_count=0,
            )

        # Execute queries with concurrency limit
        semaphore = asyncio.Semaphore(self._max_concurrent)
        results = []

        async def execute_one(item: BatchQueryItem, decision: AutoModeDecision) -> BatchQueryResult:
            async with semaphore:
                return await self._execute_single(
                    item=item,
                    decision=decision,
                    batch_id=batch_id,
                    progress_callback=progress_callback,
                )

        # Create tasks
        tasks = [execute_one(item, decision) for item, decision in zip(items, routing.decisions)]

        # Execute all
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        final_results = []
        success_count = 0
        failure_count = 0
        total_actual = 0.0

        for result in results:
            if isinstance(result, Exception):
                # Task raised exception
                failure_count += 1
                final_results.append(
                    BatchQueryResult(
                        query="unknown",
                        decision=routing.decisions[0] if routing.decisions else None,
                        success=False,
                        error=str(result),
                    )
                )
            else:
                final_results.append(result)
                if result.success:
                    success_count += 1
                    total_actual += result.cost_actual
                else:
                    failure_count += 1

        return BatchResult(
            batch_id=batch_id,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            results=final_results,
            total_cost_estimated=routing.total_cost_estimate,
            total_cost_actual=total_actual,
            success_count=success_count,
            failure_count=failure_count,
        )

    async def _execute_single(
        self,
        item: BatchQueryItem,
        decision: AutoModeDecision,
        batch_id: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> BatchQueryResult:
        """Execute a single query from the batch.

        Args:
            item: The batch query item
            decision: Routing decision for this query
            batch_id: Batch identifier
            progress_callback: Optional progress callback

        Returns:
            BatchQueryResult with execution results
        """
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode

        # Override routing if forced
        provider = item.force_provider or decision.provider
        model = item.force_model or decision.model

        if progress_callback:
            progress_callback(f"Starting: {item.query[:40]}... → {provider}/{model}")

        try:
            # Create minimal output context for batch execution
            output_context = OutputContext(mode=OutputMode.QUIET)

            # Execute the research
            await _run_single(
                query=item.query,
                model=model,
                provider=provider,
                no_web=False,
                no_code=False,
                upload=(),
                limit=item.cost_limit,
                yes=True,  # Skip confirmation in batch mode
                output_context=output_context,
                no_fallback=False,
                user_specified_provider=bool(item.force_provider),
            )

            if progress_callback:
                progress_callback(f"Completed: {item.query[:40]}...")

            return BatchQueryResult(
                query=item.query,
                decision=decision,
                success=True,
                cost_actual=decision.cost_estimate,  # Use estimate as actual for now
            )

        except Exception as e:
            if progress_callback:
                progress_callback(f"Failed: {item.query[:40]}... - {e}")

            return BatchQueryResult(
                query=item.query,
                decision=decision,
                success=False,
                error=str(e),
            )


def format_batch_preview(routing: BatchRoutingResult) -> str:
    """Format batch routing preview for display.

    Args:
        routing: BatchRoutingResult from preview

    Returns:
        Formatted string for CLI output
    """
    lines = [
        "Batch Research (--auto mode)",
        "────────────────────────────",
        f"Queries: {len(routing.decisions)}",
        "",
        "Pre-routing:",
    ]

    # Group by complexity
    for complexity in ["simple", "moderate", "complex"]:
        if complexity in routing.summary:
            stats = routing.summary[complexity]
            count = stats["count"]
            cost = stats["cost_estimate"]

            # Find primary model for this complexity
            models = stats.get("models", {})
            primary_model = max(models.items(), key=lambda x: x[1])[0] if models else "unknown"

            lines.append(f"  • {complexity.capitalize()} ({primary_model}): {count} queries, ~${cost:.2f}")

    lines.extend(
        [
            "",
            f"Estimated total: ${routing.total_cost_estimate:.2f}",
        ]
    )

    return "\n".join(lines)
