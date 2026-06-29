"""Auto mode router for intelligent query routing based on complexity.

Routes queries to the best available model using benchmark data to rank
models by measured quality per task type. Falls back to cheapest available
model when no benchmark data exists.

When benchmark results exist in the configured benchmarks directory, the
router uses per-task-type quality rankings to select the best model whose
provider has an API key configured.

Models added to the registry without benchmark data receive provisional
quality scores derived from pricing tier and specializations, so they
participate in routing immediately. Background auto-eval refines these
estimates when new models are detected.

This enables processing 20+ queries for $1-2 instead of $20-40.
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import time as _time
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from deepr.config import runtime_data_path
from deepr.experts.router import ModelRouter
from deepr.observability.provider_router import AutonomousProviderRouter
from deepr.providers.registry import MODEL_CAPABILITIES


@dataclass
class AutoModeDecision:
    """Routing decision for a query in auto mode.

    Attributes:
        provider: Selected provider (openai, xai, gemini)
        model: Selected model name
        complexity: Query complexity (simple, moderate, complex)
        task_type: Detected task type (factual, reasoning, research, coding, etc.)
        cost_estimate: Estimated cost in dollars
        confidence: Confidence in routing decision (0-1)
        reasoning: Human-readable explanation of routing choice
    """

    provider: str
    model: str
    complexity: Literal["simple", "moderate", "complex"]
    task_type: str
    cost_estimate: float
    confidence: float
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        d = {
            "provider": self.provider,
            "model": self.model,
            "complexity": self.complexity,
            "task_type": self.task_type,
            "cost_estimate": self.cost_estimate,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    def preview_text(self) -> str:
        """Return a human-readable preview of this routing decision."""
        conf_pct = f"{self.confidence * 100:.0f}%"
        lines = [
            f"  Provider:   {self.provider}",
            f"  Model:      {self.model}",
            f"  Complexity: {self.complexity}",
            f"  Task type:  {self.task_type}",
            f"  Est. cost:  ${self.cost_estimate:.4f}",
            f"  Confidence: {conf_pct}",
            f"  Reasoning:  {self.reasoning}",
        ]
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: dict) -> "AutoModeDecision":
        """Create from dictionary."""
        return cls(
            provider=data["provider"],
            model=data["model"],
            complexity=data["complexity"],
            task_type=data["task_type"],
            cost_estimate=data["cost_estimate"],
            confidence=data["confidence"],
            reasoning=data["reasoning"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class BatchRoutingResult:
    """Result of routing a batch of queries.

    Attributes:
        decisions: List of routing decisions for each query
        summary: Summary statistics by complexity/model
        total_cost_estimate: Total estimated cost for all queries
    """

    decisions: list[AutoModeDecision]
    summary: dict[str, dict]
    total_cost_estimate: float


# Provider -> environment variable mapping for API key checks
_PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "azure": "AZURE_OPENAI_KEY",
    "azure-foundry": "AZURE_PROJECT_ENDPOINT",
}


def _has_api_key(provider: str) -> bool:
    """Check if an API key is configured for the given provider.

    Args:
        provider: Provider name (openai, xai, gemini, etc.)

    Returns:
        True if the provider has an API key set in the environment
    """
    env_var = _PROVIDER_KEY_ENV.get(provider)
    if not env_var:
        return False
    return bool(os.environ.get(env_var))


_logger = logging.getLogger(__name__)

# Ranking entry: (provider, model, quality_score, cost_per_query)
_RankingEntry = tuple[str, str, float, float]


def _load_benchmark_rankings() -> dict[str, list[_RankingEntry]] | None:
    """Load latest benchmark and build per-task-type rankings.

    Returns dict: task_type -> [(provider, model, quality_score, cost_per_query), ...]
    sorted by quality desc (cost as tiebreaker). Also includes "_overall" key
    for fallback. Returns None if no benchmark data found.
    """
    bench_dir = runtime_data_path("benchmarks")
    if not bench_dir.exists():
        return None

    files = sorted(bench_dir.glob("benchmark_*.json"))
    if not files:
        return None

    latest = files[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        _logger.warning("Could not load benchmark data from %s: %s", latest, exc)
        return None

    rankings_data = data.get("rankings", [])
    if not rankings_data:
        return None

    # Merge scores across tiers for the same model (take best score per task type)
    # Only include models that are still in the registry (benchmark data may
    # reference removed/superseded models from prior runs).
    model_scores: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rankings_data:
        model_key = r.get("model_key", "")
        if "/" not in model_key:
            continue
        if model_key not in MODEL_CAPABILITIES:
            continue
        for task_type, score in r.get("scores_by_type", {}).items():
            prev = model_scores[model_key].get(task_type, 0)
            if score > prev:
                model_scores[model_key][task_type] = score

    # Build per-task-type rankings
    all_task_types: set[str] = set()
    for scores in model_scores.values():
        all_task_types.update(scores.keys())

    rankings: dict[str, list[_RankingEntry]] = {}
    for task_type in all_task_types:
        ranked: list[_RankingEntry] = []
        for model_key, scores in model_scores.items():
            if task_type not in scores:
                continue
            quality = scores[task_type]
            cap = MODEL_CAPABILITIES.get(model_key)
            cost = cap.cost_per_query if cap else 0.10
            provider, model = model_key.split("/", 1)
            ranked.append((provider, model, quality, cost))
        # Sort by quality desc, then cost asc as tiebreaker
        ranked.sort(key=lambda r: (-r[2], r[3]))
        rankings[task_type] = ranked

    # Build _overall: deduplicated, by avg quality across all task types
    overall_quality: dict[str, float] = {}
    for model_key, scores in model_scores.items():
        if scores:
            overall_quality[model_key] = sum(scores.values()) / len(scores)

    overall: list[_RankingEntry] = []
    for model_key in sorted(overall_quality, key=overall_quality.get, reverse=True):
        if "/" not in model_key:
            continue
        provider, model = model_key.split("/", 1)
        cap = MODEL_CAPABILITIES.get(model_key)
        cost = cap.cost_per_query if cap else 0.10
        overall.append((provider, model, overall_quality[model_key], cost))
    rankings["_overall"] = overall

    return rankings


# ─── Provisional Rankings ─────────────────────────────────────────────────────
# Models without benchmark data get synthetic quality scores from registry
# metadata so they participate in routing immediately.

# Map registry specializations -> benchmark task types
_SPEC_TO_TASK_TYPES: dict[str, list[str]] = {
    "speed": ["quick_lookup"],
    "factual": ["quick_lookup", "knowledge_base"],
    "reasoning": ["reasoning", "knowledge_base"],
    "research": ["comprehensive_research", "synthesis"],
    "analysis": ["document_analysis", "synthesis"],
    "synthesis": ["synthesis", "comprehensive_research"],
    "coding": ["technical_docs"],
    "news": ["quick_lookup"],
    "general": ["quick_lookup", "knowledge_base"],
    "high_throughput": ["quick_lookup"],
    "agentic": ["comprehensive_research", "synthesis"],
    "tool_calling": ["comprehensive_research", "technical_docs"],
    "instruction_following": ["reasoning", "technical_docs"],
    "cost": ["quick_lookup"],
    "developer_workflows": ["technical_docs"],
}


def _estimate_quality(cap) -> float:
    """Provisional quality for an unbenchmarked model (<= 0.78).

    Prefer a published-benchmark-derived prior (``quality_priors``) when one
    exists - that reflects real capability independent of price, so a
    cheap-but-capable model is not under-ranked just for being cheap. Fall back
    to the crude price-tier heuristic only when no prior exists. Either way the
    result is capped at 0.78 so measured eval scores (up to 1.0) always sort
    above provisional entries.
    """
    from deepr.routing.quality_priors import get_quality_prior

    prior = get_quality_prior(cap.provider, cap.model)
    if prior is not None:
        return min(0.78, max(0.0, float(prior)))
    output_cost = cap.output_cost_per_1m
    if output_cost >= 10.0:
        return 0.78  # Frontier (Opus, GPT-5, deep research)
    if output_cost >= 4.0:
        return 0.72  # Strong (o3, Sonnet, Gemini Pro, Grok 4.20)
    if output_cost >= 1.5:
        return 0.65  # Mid (Flash, grok-code-fast)
    if output_cost >= 0.4:
        return 0.58  # Budget (nano, flash-lite)
    return 0.50  # Ultra-cheap


def _enrich_with_provisional(
    real_rankings: dict[str, list[_RankingEntry]] | None,
) -> dict[str, list[_RankingEntry]] | None:
    """Merge provisional entries for unbenchmarked models into real rankings.

    Models already in real_rankings are skipped. Provisional quality is capped
    at 0.78 so verified benchmark winners always sort higher.
    """
    rankings: dict[str, list[_RankingEntry]] = {}
    if real_rankings:
        rankings = {k: list(v) for k, v in real_rankings.items()}

    # Collect models that already have real benchmark data
    benchmarked: set[str] = set()
    if real_rankings:
        for entries in real_rankings.values():
            for provider, model, _q, _c in entries:
                benchmarked.add(f"{provider}/{model}")

    # Generate provisional entries for unbenchmarked registry models
    added = 0
    for model_key, cap in MODEL_CAPABILITIES.items():
        if model_key in benchmarked:
            continue
        # Skip deprecated models - they shouldn't participate in routing
        if cap.deprecated:
            continue

        quality = _estimate_quality(cap)
        provider, model = model_key.split("/", 1)
        entry: _RankingEntry = (provider, model, quality, cap.cost_per_query)

        # Map specializations to task types
        task_types: set[str] = set()
        for spec in cap.specializations:
            task_types.update(_SPEC_TO_TASK_TYPES.get(spec, []))
        task_types.add("quick_lookup")  # Every model gets at least quick_lookup

        for tt in task_types:
            rankings.setdefault(tt, []).append(entry)
        rankings.setdefault("_overall", []).append(entry)
        added += 1

    if added:
        _logger.debug("Added %d provisional ranking entries for unbenchmarked models", added)

    # Re-sort all lists: quality desc, cost asc
    for tt in rankings:
        rankings[tt].sort(key=lambda r: (-r[2], r[3]))

    return rankings if rankings else None


# ─── Hot-Reload Cache ─────────────────────────────────────────────────────────
# Rankings are served through a function with mtime-based invalidation instead
# of a module-level constant, so background eval results are picked up live.

_rankings_cache: dict[str, list[_RankingEntry]] | None = None
_rankings_mtime: float = 0.0
_rankings_check_ts: float = 0.0
_RANKINGS_CHECK_INTERVAL = 5.0  # seconds between filesystem stat calls


def _get_benchmark_rankings() -> dict[str, list[_RankingEntry]] | None:
    """Return benchmark rankings, reloading from disk if the file changed.

    Checks file mtime at most every 5 seconds. Enriches with provisional
    entries for any registry models without benchmark data.
    """
    global _rankings_cache, _rankings_mtime, _rankings_check_ts

    now = _time.monotonic()
    if now - _rankings_check_ts < _RANKINGS_CHECK_INTERVAL and _rankings_cache is not None:
        return _rankings_cache

    _rankings_check_ts = now

    bench_dir = runtime_data_path("benchmarks")
    if not bench_dir.exists():
        if _rankings_cache is None:
            _rankings_cache = _enrich_with_provisional(None)
        return _rankings_cache

    files = sorted(bench_dir.glob("benchmark_*.json"))
    if not files:
        if _rankings_cache is None:
            _rankings_cache = _enrich_with_provisional(None)
        return _rankings_cache

    latest = files[-1]
    try:
        mtime = latest.stat().st_mtime
    except OSError:
        return _rankings_cache

    if mtime != _rankings_mtime or _rankings_cache is None:
        _rankings_mtime = mtime
        loaded = _load_benchmark_rankings()
        _rankings_cache = _enrich_with_provisional(loaded)
        _logger.info("Reloaded benchmark rankings from %s", latest.name)

    return _rankings_cache


# ─── Background Auto-Eval ─────────────────────────────────────────────────────
# When new models are added to the registry, automatically run quick evals
# in the background so routing data stays current.

_auto_eval_started = False
_auto_eval_lock = threading.Lock()


def _compute_registry_hash() -> str:
    """Compute a stable hash of all registry model keys."""
    keys = sorted(MODEL_CAPABILITIES.keys())
    return hashlib.sha256("|".join(keys).encode()).hexdigest()[
        :16
    ]  # stable short hash for registry change detection (sha256 for collision resistance)


def _run_benchmark_eval(cost_cap: float, hash_file: Path, current_hash: str) -> None:
    """Run the cost-capped registry-change benchmark in a background thread.

    benchmark_models.py lives in the repo's scripts/ dir (repo root = parents[3]
    of this module). It is not shipped in the installed package, so degrade
    quietly when absent (e.g. a pipx install) rather than failing the subprocess.
    """
    try:
        script = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_models.py"
        if not script.exists():
            _logger.debug("Skipping background eval: benchmark script not found at %s", script)
            return
        result = subprocess.run(  # Internal trusted benchmark_models.py; no user-controlled input; background cost-capped eval.
            [
                sys.executable,
                str(script),
                "--new-models",
                "--tier",
                "all",
                "--quick",
                "--save",
                "--max-estimated-cost",
                str(cost_cap),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            hash_file.parent.mkdir(parents=True, exist_ok=True)
            hash_file.write_text(current_hash)
            _logger.info("Background eval completed successfully")
        else:
            _logger.warning("Background eval failed (rc=%d): %s", result.returncode, result.stderr[:200])
    except subprocess.TimeoutExpired:
        _logger.warning("Background eval timed out after 10 minutes")
    except Exception as exc:
        _logger.warning("Background eval error: %s", exc)


def trigger_background_eval_if_needed(
    cost_cap: float = 1.0,
    enabled: bool | None = None,
) -> bool:
    """Check for new models and start background eval if gaps detected.

    Compares a hash of registry model keys against a stored hash file.
    If they differ, spawns a daemon thread running ``deepr eval new --quick``.

    Args:
        cost_cap: Maximum estimated cost for the background eval run.
        enabled: Override for DEEPR_AUTO_EVAL env var. None = check env.

    Returns:
        True if a background eval was started, False otherwise.
    """
    global _auto_eval_started

    if enabled is None:
        enabled = os.environ.get("DEEPR_AUTO_EVAL", "true").lower() not in (
            "false",
            "0",
            "no",
            "off",
        )
    if not enabled:
        return False

    with _auto_eval_lock:
        if _auto_eval_started:
            return False
        _auto_eval_started = True

    hash_file = runtime_data_path("benchmarks", ".registry_hash")
    current_hash = _compute_registry_hash()

    with suppress(OSError):
        if hash_file.exists() and hash_file.read_text().strip() == current_hash:
            return False

    _logger.info(
        "New models detected in registry, starting background eval (cost cap: $%.2f)",
        cost_cap,
    )

    thread = threading.Thread(
        target=_run_benchmark_eval,
        args=(cost_cap, hash_file, current_hash),
        daemon=True,
        name="deepr-auto-eval",
    )
    thread.start()
    return True


# Map (complexity, task_type) to benchmark task types
_TASK_MAP = {
    ("simple", "factual"): "quick_lookup",
    ("simple", "reasoning"): "knowledge_base",
    ("simple", "coding"): "knowledge_base",
    ("simple", "research"): "quick_lookup",
    ("simple", "document_analysis"): "document_analysis",
    ("moderate", "factual"): "knowledge_base",
    ("moderate", "reasoning"): "reasoning",
    ("moderate", "research"): "synthesis",
    ("moderate", "coding"): "technical_docs",
    ("moderate", "document_analysis"): "document_analysis",
    ("complex", "research"): "comprehensive_research",
    ("complex", "reasoning"): "reasoning",
    ("complex", "coding"): "technical_docs",
    ("complex", "document_analysis"): "document_analysis",
    ("complex", "factual"): "knowledge_base",
}

# Reasoning effort mapping based on query complexity (for Grok 4.3)
COMPLEXITY_TO_REASONING_EFFORT: dict[str, str] = {
    "simple": "low",
    "moderate": "medium",
    "complex": "high",
}


def _apply_reasoning_effort(decision: AutoModeDecision) -> AutoModeDecision:
    """Set reasoning_effort metadata when Grok 4.3 is selected.

    Maps query complexity to reasoning effort level and stores it in
    the decision metadata for downstream use by the provider.
    """
    if "grok-4.3" in decision.model or "grok-4-3" in decision.model:
        effort = COMPLEXITY_TO_REASONING_EFFORT.get(decision.complexity, "medium")
        decision.metadata["reasoning_effort"] = effort
    return decision


class AutoModeRouter:
    """Routes queries to optimal models based on benchmark quality data.

    Uses benchmark rankings to select the best available model for each
    task type, filtered by which providers have API keys configured.

    Example:
        router = AutoModeRouter()
        decision = router.route("What is Python?")
        # -> benchmark winner for quick_lookup with available API key
    """

    def __init__(
        self,
        model_router: ModelRouter | None = None,
        provider_router: AutonomousProviderRouter | None = None,
    ):
        """Initialize auto mode router.

        Args:
            model_router: Optional ModelRouter instance (creates one if not provided)
            provider_router: Optional AutonomousProviderRouter (creates one if not provided)
        """
        self._model_router = model_router or ModelRouter()
        self._provider_router = provider_router or AutonomousProviderRouter()

        # Cache which providers have API keys configured
        self._available_providers = {p for p in _PROVIDER_KEY_ENV if _has_api_key(p)}

        # Trigger background eval for new/unbenchmarked models (non-blocking)
        trigger_background_eval_if_needed()

    def _is_provider_usable(self, provider: str) -> bool:
        """Check if a provider has an API key configured.

        Args:
            provider: Provider name

        Returns:
            True if provider has an API key configured
        """
        return provider in self._available_providers

    def route(
        self,
        query: str,
        budget: float | None = None,
        prefer_cost: bool = False,
        prefer_speed: bool = False,
    ) -> AutoModeDecision:
        """Route a single query to the optimal model.

        Args:
            query: The research query
            budget: Maximum budget for this query (None = unlimited)
            prefer_cost: If True, prefer cheaper options when uncertain
            prefer_speed: If True, prefer faster options when uncertain

        Returns:
            AutoModeDecision with provider, model, and metadata
        """
        from deepr.routing.deprecation import migrate_model

        # Analyze query complexity and task type
        complexity = self._model_router._classify_complexity(query)
        task_type = self._model_router._detect_task_type(query)

        # Get model recommendation from ModelRouter (for confidence score)
        model_config = self._model_router.select_model(
            query=query,
            budget_remaining=budget,
        )

        # Route using benchmark data
        provider, model, cost_estimate, reasoning = self._apply_auto_rules(
            complexity=complexity,
            task_type=task_type,
            budget=budget,
            prefer_cost=prefer_cost,
            prefer_speed=prefer_speed,
        )

        # Check provider health from autonomous router
        if not self._provider_router.is_circuit_available(provider, model):
            provider, model, cost_estimate, reasoning = self._get_fallback(complexity, task_type, budget)

        # Check for deprecated model and auto-migrate
        metadata: dict[str, Any] = {}
        resolved_model, confidence, migration_warning = migrate_model(model, confidence=model_config.confidence)
        if migration_warning is not None:
            metadata["migrated_from"] = model
            model = resolved_model
            # Update provider if successor includes provider prefix
            if "/" in model:
                provider, model = model.split("/", 1)

        decision = AutoModeDecision(
            provider=provider,
            model=model,
            complexity=complexity,
            task_type=task_type,
            cost_estimate=cost_estimate,
            confidence=confidence,
            reasoning=reasoning,
            metadata=metadata,
        )

        # Apply reasoning effort for Grok 4.3
        decision = _apply_reasoning_effort(decision)

        return decision

    def route_batch(
        self,
        queries: list[str],
        budget_total: float | None = None,
        prefer_cost: bool = False,
    ) -> BatchRoutingResult:
        """Route a batch of queries with optional total budget constraint.

        Args:
            queries: List of research queries
            budget_total: Maximum total budget for all queries (None = unlimited)
            prefer_cost: If True, prefer cheaper options

        Returns:
            BatchRoutingResult with decisions and summary
        """
        decisions = []
        remaining_budget = budget_total

        # First pass: route all queries optimally
        for query in queries:
            per_query_budget = None
            if remaining_budget is not None:
                # Distribute remaining budget proportionally
                queries_left = len(queries) - len(decisions)
                per_query_budget = remaining_budget / queries_left if queries_left > 0 else 0

            decision = self.route(
                query=query,
                budget=per_query_budget,
                prefer_cost=prefer_cost or (budget_total is not None),
            )
            decisions.append(decision)

            if remaining_budget is not None:
                remaining_budget -= decision.cost_estimate
                # Ensure we don't go negative
                remaining_budget = max(0, remaining_budget)

        # Build summary
        summary = self._build_summary(decisions)
        total_cost = sum(d.cost_estimate for d in decisions)

        return BatchRoutingResult(
            decisions=decisions,
            summary=summary,
            total_cost_estimate=total_cost,
        )

    def _pick_provider(self, preferred: str, *fallbacks: str) -> str:
        """Pick the first usable provider from the given preference order.

        Args:
            preferred: First-choice provider
            *fallbacks: Backup providers in priority order

        Returns:
            The first provider with a configured API key,
            or the preferred provider as last resort
        """
        if self._is_provider_usable(preferred):
            return preferred
        for fb in fallbacks:
            if self._is_provider_usable(fb):
                return fb
        if not self._available_providers:
            raise ValueError(
                "No API keys configured. Set at least one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, XAI_API_KEY"
            )
        return preferred  # Has key but circuit may be open

    def _best_available(
        self,
        task_type: str,
        budget: float | None,
        prefer_cost: bool,
    ) -> tuple[str, str, float, float] | None:
        """Find the best available model for a task type from benchmark rankings.

        Walks the ranked list and returns the first model whose provider has
        an API key and whose cost fits within budget.

        Args:
            task_type: Benchmark task type key
            budget: Maximum cost (None = unlimited)
            prefer_cost: If True, sort by cost-per-quality instead of raw quality

        Returns:
            (provider, model, cost, quality_score) or None
        """
        if not _get_benchmark_rankings():
            return None

        ranked = _get_benchmark_rankings().get(task_type)
        if not ranked:
            return None

        if prefer_cost:
            # Re-sort by cost-per-quality ascending (best value first)
            ranked = sorted(ranked, key=lambda r: r[3] / max(r[2], 0.001))

        from deepr.routing.deprecation import check_deprecation

        for provider, model, quality, cost in ranked:
            if not self._is_provider_usable(provider):
                continue
            if budget is not None and cost > budget:
                continue
            # Skip deprecated models - route to successor if available
            dep = check_deprecation(model)
            if dep is not None:
                continue
            return (provider, model, cost, quality)

        return None

    def _cheapest_available(self, budget: float | None) -> tuple[str, str, float, str]:
        """Find the cheapest available model from the registry.

        Used as last resort when no benchmark data exists or all benchmark
        models are filtered out.

        Returns:
            Tuple of (provider, model, cost_estimate, reasoning)
        """
        from deepr.routing.deprecation import check_deprecation

        candidates = []
        for cap in MODEL_CAPABILITIES.values():
            if self._is_provider_usable(cap.provider):
                if budget is None or cap.cost_per_query <= budget:
                    if check_deprecation(cap.model) is None:
                        candidates.append((cap.provider, cap.model, cap.cost_per_query))

        if candidates:
            candidates.sort(key=lambda x: x[2])  # Cheapest first
            p, m, c = candidates[0]
            return (p, m, c, f"Cheapest available -> {p}/{m} (${c:.3f})")

        # Absolute last resort - but pick a USABLE provider. The previous
        # behaviour hard-coded ``openai/gpt-4.1-mini`` regardless of
        # which providers had API keys, so a user with only Gemini/XAI
        # configured would receive an openai model the dispatcher
        # couldn't actually call.
        for cap in sorted(MODEL_CAPABILITIES.values(), key=lambda c: c.cost_per_query):
            if self._is_provider_usable(cap.provider) and check_deprecation(cap.model) is None:
                return (
                    cap.provider,
                    cap.model,
                    cap.cost_per_query,
                    f"Last resort (no candidates under budget) -> {cap.provider}/{cap.model}",
                )

        # If we reach here, no provider is usable at all. Surface that
        # honestly rather than handing back a model that will fail at
        # provider creation.
        raise RuntimeError(
            "No provider with credentials is configured; cannot route research. "
            "Set at least one of: OPENAI_API_KEY, GEMINI_API_KEY, XAI_API_KEY, ANTHROPIC_API_KEY."
        )

    def _apply_auto_rules(
        self,
        complexity: str,
        task_type: str,
        budget: float | None,
        prefer_cost: bool,
        prefer_speed: bool,
    ) -> tuple:
        """Route using benchmark quality rankings.

        Maps (complexity, task_type) to a benchmark task type, then picks
        the highest-quality available model. Falls back to overall rankings,
        then to cheapest available model.

        Returns:
            Tuple of (provider, model, cost_estimate, reasoning)
        """
        bench_task = _TASK_MAP.get((complexity, task_type), task_type)
        use_value = prefer_cost or prefer_speed

        # Try benchmark-ranked model for specific task
        result = self._best_available(bench_task, budget, use_value)
        if result:
            provider, model, cost, score = result
            return (
                provider,
                model,
                cost,
                f"Benchmark: {bench_task} -> {provider}/{model} (quality: {score:.0%}, ${cost:.2f})",
            )

        # Fallback to overall ranking
        result = self._best_available("_overall", budget, use_value)
        if result:
            provider, model, cost, score = result
            return (
                provider,
                model,
                cost,
                f"Overall best available -> {provider}/{model}",
            )

        # Last resort: cheapest available from registry
        return self._cheapest_available(budget)

    def _get_fallback(
        self,
        complexity: str,
        task_type: str,
        budget: float | None,
    ) -> tuple:
        """Get fallback routing when primary provider circuit is open.

        Checks both API key availability and circuit breaker state.

        Returns:
            Tuple of (provider, model, cost_estimate, reasoning)
        """
        # Try gemini as fallback for complex queries
        if complexity == "complex" and self._is_provider_usable("gemini"):
            if self._provider_router.is_circuit_available("gemini", "gemini-3.1-pro-preview"):
                return (
                    "gemini",
                    "gemini-3.1-pro-preview",
                    0.20,
                    "Fallback to gemini-3.1-pro-preview (primary provider unavailable)",
                )

        # Try o4-mini as lighter OpenAI fallback for complex queries
        if complexity in ("complex", "moderate") and self._is_provider_usable("openai"):
            if self._provider_router.is_circuit_available("openai", "o4-mini-deep-research"):
                return (
                    "openai",
                    "o4-mini-deep-research",
                    0.10,
                    "Fallback to o4-mini-deep-research (primary circuit open)",
                )

        # Try grok as universal fallback
        if self._is_provider_usable("xai"):
            if self._provider_router.is_circuit_available("xai", "grok-4-3"):
                return (
                    "xai",
                    "grok-4-3",
                    0.05,
                    "Fallback to grok-4-3 (primary provider unavailable)",
                )

        # Last resort: ask ``_cheapest_available`` which iterates the
        # usable providers and raises ``RuntimeError`` if none have keys.
        # Round-3 fixed this exact pattern in ``_cheapest_available`` but
        # missed this sibling path - handing back ``openai/gpt-4.1-mini``
        # when no OpenAI key is configured produced a fail-at-provider-
        # creation downstream and a confusing error.
        return self._cheapest_available(budget=None)

    def _build_summary(self, decisions: list[AutoModeDecision]) -> dict[str, dict]:
        """Build summary statistics from routing decisions.

        Returns:
            Dictionary mapping complexity to stats
        """
        summary = {}

        for decision in decisions:
            key = f"{decision.complexity}"
            if key not in summary:
                summary[key] = {
                    "count": 0,
                    "cost_estimate": 0.0,
                    "models": {},
                }

            summary[key]["count"] += 1
            summary[key]["cost_estimate"] += decision.cost_estimate

            model_key = f"{decision.provider}/{decision.model}"
            if model_key not in summary[key]["models"]:
                summary[key]["models"][model_key] = 0
            summary[key]["models"][model_key] += 1

        return summary

    def explain_routing(self, query: str) -> str:
        """Generate detailed explanation of routing decision.

        Args:
            query: The query to explain routing for

        Returns:
            Human-readable explanation
        """
        decision = self.route(query)
        complexity = decision.complexity
        task_type = decision.task_type

        explanation = f"""
Query Analysis
──────────────
Query: {query[:80]}{"..." if len(query) > 80 else ""}
Complexity: {complexity}
Task Type: {task_type}

Routing Decision
────────────────
Provider: {decision.provider}
Model: {decision.model}
Cost Estimate: ${decision.cost_estimate:.2f}
Confidence: {decision.confidence:.0%}

Reasoning
─────────
{decision.reasoning}
"""
        return explanation.strip()
