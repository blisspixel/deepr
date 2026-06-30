"""
Tool Registry with BM25/semantic search for dynamic tool discovery.

This module maintains a searchable index of all Deepr tools, enabling
the gateway pattern that reduces initial context by ~85%.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from deepr.mcp.consult_tool import CONSULT_EXPERTS_INPUT_SCHEMA, CONSULT_EXPERTS_OUTPUT_SCHEMA
from deepr.mcp.query_expert_tool import QUERY_EXPERT_INPUT_SCHEMA


@dataclass
class ToolSchema:
    """Schema for a single MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    category: str = "general"
    cost_tier: str = "free"  # free, low, medium, high
    output_schema: dict[str, Any] | None = None

    _tokens: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        """Tokenize description for search indexing."""
        if not self._tokens:
            self._tokens = self._tokenize(f"{self.name} {self.description} {self.category}")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple tokenization for BM25 indexing."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        return [t for t in text.split() if len(t) > 2]

    @property
    def tokens(self) -> list[str]:
        return self._tokens

    def to_mcp_format(self) -> dict[str, Any]:
        """Convert to MCP tool format."""
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.output_schema is not None:
            payload["outputSchema"] = self.output_schema
        return payload


class BM25Index:
    """
    Simple BM25 implementation for tool search.

    BM25 (Best Matching 25) is a ranking function used by search engines
    to estimate the relevance of documents to a given search query.

    Parameters:
        k1: Term frequency saturation parameter (default 1.5)
        b: Length normalization parameter (default 0.75)

    Note:
        This implementation handles edge cases like empty corpus and
        queries with no matching terms gracefully.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Initialize BM25 index.

        Args:
            k1: Controls term frequency saturation. Higher values give
                more weight to term frequency. Typical range: 1.2-2.0
            b: Controls document length normalization. 0 = no normalization,
               1 = full normalization. Typical value: 0.75
        """
        self.k1 = k1
        self.b = b
        self._corpus: list[list[str]] = []
        self._doc_lengths: list[int] = []
        self._avg_doc_length: float = 0.0
        self._doc_freqs: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._n_docs: int = 0

    def fit(self, corpus: list[list[str]]) -> None:
        """
        Build index from corpus of tokenized documents.

        Args:
            corpus: List of documents, where each document is a list of tokens

        Note:
            Empty corpus is handled gracefully - searches will return empty results.
        """
        self._corpus = corpus
        self._n_docs = len(corpus)

        # Handle empty corpus
        if self._n_docs == 0:
            self._doc_lengths = []
            self._avg_doc_length = 0.0
            self._doc_freqs = {}
            self._idf = {}
            return

        self._doc_lengths = [len(doc) for doc in corpus]
        total_length = sum(self._doc_lengths)
        self._avg_doc_length = total_length / self._n_docs if self._n_docs > 0 else 0.0

        # Calculate document frequencies
        self._doc_freqs = {}
        for doc in corpus:
            seen = set()
            for token in doc:
                if token not in seen:
                    self._doc_freqs[token] = self._doc_freqs.get(token, 0) + 1
                    seen.add(token)

        # Calculate IDF scores
        import math

        self._idf = {}
        for token, df in self._doc_freqs.items():
            # Using BM25 IDF formula with smoothing to avoid negative values
            self._idf[token] = math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1)

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        """
        Calculate BM25 scores for all documents given query.

        Args:
            query_tokens: List of query tokens

        Returns:
            List of scores, one per document in corpus order.
            Empty list if corpus is empty.
        """
        # Handle empty corpus or query
        if not self._corpus or not query_tokens:
            return [0.0] * len(self._corpus)

        scores = []

        for idx, doc in enumerate(self._corpus):
            score = 0.0
            doc_len = self._doc_lengths[idx]

            # Count term frequencies in document
            term_freqs: dict[str, int] = {}
            for token in doc:
                term_freqs[token] = term_freqs.get(token, 0) + 1

            for token in query_tokens:
                if token not in self._idf:
                    continue

                tf = term_freqs.get(token, 0)
                idf = self._idf[token]

                # BM25 formula with safe division
                numerator = tf * (self.k1 + 1)
                # Avoid division by zero when avg_doc_length is 0
                if self._avg_doc_length > 0:
                    denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self._avg_doc_length)
                else:
                    denominator = tf + self.k1

                if denominator > 0:
                    score += idf * (numerator / denominator)

            scores.append(score)

        return scores


class ToolRegistry:
    """
    Registry of all Deepr tools with search capability.

    Implements the Dynamic Tool Discovery pattern by maintaining
    a searchable index of tools that can be queried by natural language.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSchema] = {}
        self._index: BM25Index | None = None
        self._tool_order: list[str] = []  # Maintain insertion order

    def register(self, tool: ToolSchema) -> None:
        """Register a tool in the registry."""
        self._tools[tool.name] = tool
        if tool.name not in self._tool_order:
            self._tool_order.append(tool.name)
        self._rebuild_index()

    def register_many(self, tools: list[ToolSchema]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self._tools[tool.name] = tool
            if tool.name not in self._tool_order:
                self._tool_order.append(tool.name)
        self._rebuild_index()

    def get(self, name: str) -> ToolSchema | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def search(self, query: str, limit: int = 3) -> list[ToolSchema]:
        """
        Search for tools matching a natural language query.

        Args:
            query: Natural language description of desired capability
            limit: Maximum number of tools to return

        Returns:
            List of matching ToolSchema objects, ranked by relevance
        """
        if not self._index or not self._tools:
            return []

        query_tokens = ToolSchema._tokenize(query)
        if not query_tokens:
            return []

        scores = self._index.get_scores(query_tokens)

        # Pair tools with scores and sort
        tool_scores = [
            (self._tools[name], scores[idx]) for idx, name in enumerate(self._tool_order) if name in self._tools
        ]

        # Sort by score descending, filter zero scores
        ranked = sorted([(t, s) for t, s in tool_scores if s > 0], key=lambda x: x[1], reverse=True)

        return [tool for tool, _ in ranked[:limit]]

    def all_tools(self) -> list[ToolSchema]:
        """Get all registered tools."""
        return [self._tools[name] for name in self._tool_order if name in self._tools]

    def count(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)

    def _rebuild_index(self) -> None:
        """Rebuild the BM25 index after tool changes."""
        if not self._tools:
            self._index = None
            return

        corpus = [self._tools[name].tokens for name in self._tool_order if name in self._tools]

        self._index = BM25Index()
        self._index.fit(corpus)

    def estimate_tokens(self, tools: list[ToolSchema] | None = None) -> int:
        """
        Estimate token count for tool schemas.

        Uses rough approximation: 4 chars per token.
        """
        if tools is None:
            tools = self.all_tools()

        total_chars = 0
        for tool in tools:
            # Name + description + schema JSON
            total_chars += len(tool.name)
            total_chars += len(tool.description)
            import json

            total_chars += len(json.dumps(tool.input_schema))

        return total_chars // 4


def create_default_registry() -> ToolRegistry:
    """
    Create a registry with all default Deepr tools.

    Returns:
        ToolRegistry populated with all Deepr tools
    """
    registry = ToolRegistry()

    # Discovery: the one free call a connecting agent should make first.
    registry.register(
        ToolSchema(
            name="deepr_capabilities",
            description=(
                "Discovery: one free call returning what Deepr offers and how to use it well. "
                "Returns the versioned deepr-capabilities-v1 map: the expert roster, the key "
                "tools with their cost tiers and when-to-use, the $0 owned/prepaid synthesis "
                "paths, the cost-tier legend, and the structured-error contract. Call this first "
                "when you connect."
            ),
            input_schema={"type": "object", "properties": {}},
            category="system",
            cost_tier="free",
        )
    )

    # Research tools
    registry.register(
        ToolSchema(
            name="deepr_research",
            description=(
                "Submit a deep research job for comprehensive analysis requiring web search "
                "and synthesis. Returns job_id for async status tracking and resource URIs for "
                "subscriptions. Costs $0.10-$0.50. Do NOT use for simple factual lookups -- "
                "use web search instead. Example: deepr_research(prompt='Compare HIPAA vs GDPR "
                "data retention requirements')"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Research question or topic. Be specific (e.g., 'Impact of Basel III on crypto') rather than generic.",
                    },
                    "model": {
                        "type": "string",
                        "default": "o4-mini-deep-research",
                        "description": "Model: o4-mini-deep-research ($0.15, fast), o3-deep-research ($0.50, premium)",
                    },
                    "provider": {
                        "type": "string",
                        "default": "openai",
                        "description": "Provider: openai, azure, gemini, grok",
                    },
                    "budget": {"type": "number", "description": "Maximum cost in dollars"},
                    "enable_web_search": {"type": "boolean", "default": True},
                },
                "required": ["prompt"],
            },
            category="research",
            cost_tier="medium",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_check_status",
            description=(
                "Check progress of a research job. Returns phase, progress percentage, "
                "elapsed time, and cost so far. Prefer subscribing to "
                "deepr://campaigns/{id}/status for push updates instead of polling."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job ID from deepr_research or deepr_agentic_research"},
                },
                "required": ["job_id"],
            },
            category="research",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_get_result",
            description=(
                "Get results of a completed research job. Returns markdown report with "
                "citations, cost, and metadata. Only call after deepr_check_status confirms "
                "status is 'completed'. For large reports, returns summary + resource URI."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job ID from deepr_research"},
                },
                "required": ["job_id"],
            },
            category="research",
            cost_tier="free",
        )
    )

    # Expert tools
    registry.register(
        ToolSchema(
            name="deepr_list_experts",
            description=(
                "List all available domain experts with name, domain, document count, "
                "and conversation count. Use this before querying to find the right expert."
            ),
            input_schema={
                "type": "object",
                "properties": {},
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_query_expert",
            description=(
                "Single-expert question path. Default backend='api' uses the legacy "
                "metered-capable chat session and agentic=true may trigger research. "
                "backend='local' or backend='plan' runs one read-only compiled-context "
                "turn through owned or explicit plan capacity with live metered fallback "
                "disabled and research_triggered=0."
            ),
            input_schema=QUERY_EXPERT_INPUT_SCHEMA,
            category="experts",
            cost_tier="low",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_consult_experts",
            description=(
                "Consult a TEAM of domain experts on a question and get one synthesized, "
                "calibrated answer (the deepr-consult-v1 artifact: answer, each expert's "
                "perspective with confidence, points of agreement and dissent, and cost). "
                "Routes to the most relevant experts automatically, or pass 'experts' to name "
                "them. Use synthesis_backend='local' or 'plan' to keep synthesis on owned or "
                "explicit plan capacity with live metered expert fallback disabled."
            ),
            input_schema=CONSULT_EXPERTS_INPUT_SCHEMA,
            output_schema=CONSULT_EXPERTS_OUTPUT_SCHEMA,
            category="experts",
            cost_tier="low",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_get_expert_info",
            description=(
                "Get detailed information about an expert including document count, "
                "conversation stats, knowledge gaps, and capabilities. Use to assess "
                "if an expert is suitable before querying."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_expert_manifest",
            description=(
                "Get the full ExpertManifest for an expert: all claims (beliefs with "
                "confidence and sources), knowledge gaps (scored by EV/cost), decision "
                "records, and policies. Use for comprehensive expert state inspection."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_expert_validate",
            description=(
                "Validate a claim against an expert's accumulated knowledge. Returns a "
                "structured verdict (pass/warn/fail) with confidence, reasoning, supporting "
                "and contradicting claims (with citations), and caveats for any relevant "
                "knowledge gaps. Pure read-side: does not modify the expert. Useful as a "
                "guardrail for downstream agents that need domain validation before acting. "
                "Cost: one small reasoning-model call (default gpt-5-mini). "
                "Example: deepr_expert_validate(expert_name='AI Strategy Expert', "
                "claim='GPT-5 outperforms GPT-4 on every benchmark')"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert to consult"},
                    "claim": {
                        "type": "string",
                        "description": "The statement to assess. Free text; the expert will return PASS / WARN / FAIL.",
                    },
                    "model": {
                        "type": "string",
                        "description": "Optional override for the validation model (default: gpt-5-mini)",
                    },
                    "max_evidence": {
                        "type": "integer",
                        "default": 8,
                        "description": "Maximum expert beliefs to include as grounding evidence",
                    },
                },
                "required": ["expert_name", "claim"],
            },
            category="experts",
            cost_tier="low",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_rank_gaps",
            description=(
                "Get the top N knowledge gaps for an expert ranked by expected value "
                "relative to estimated research cost. Use to decide which gaps to fill "
                "first for maximum impact."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                    "top_n": {
                        "type": "integer",
                        "default": 5,
                        "description": "Number of top gaps to return",
                    },
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_expert_health_check",
            description=(
                "Audit an expert's knowledge state. Read-only and costs nothing. Returns a "
                "structured health report - knowledge freshness, belief contradictions "
                "(heuristic), claims missing source provenance, beliefs decayed below the "
                "confidence threshold, the open-gap backlog, and ingested documents not yet "
                "synthesized - plus a recommended-action menu where each action carries its "
                "CLI command, estimated cost, and approval tier. The audit only proposes; it "
                "never mutates the expert or spends. Use to decide whether an expert needs "
                "maintenance before relying on it. "
                "Example: deepr_expert_health_check(expert_name='AI Strategy Expert')"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert to audit"},
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_expert_loop_status",
            description=(
                "Show durable loop-run status for an expert. Read-only and cost-$0. Returns "
                "schema-versioned loop runs with status, stop reason, budget/capacity source, "
                "verifier fields, acceptance metrics, and next action. Use this before scheduling "
                "or resuming expert maintenance so host agents can see blocked, waiting, pending, "
                "or completed loop work without re-running it. "
                "Example: deepr_expert_loop_status(expert_name='AI Strategy Expert', limit=5)"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum loop runs to return",
                    },
                    "status": {
                        "type": "string",
                        "description": "Optional status filter: pending, running, waiting, completed, failed, cancelled",
                    },
                    "loop_type": {
                        "type": "string",
                        "description": "Optional loop type filter, such as sync, gap_fill, or health_check",
                    },
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_semantic_recall",
            description=(
                "Recall candidate beliefs for verifier or host-agent routing. Read-only and "
                "cost-$0. Returns candidate_only belief matches, never generates embeddings, "
                "and never writes graph state. By default it uses local lexical routing; pass "
                "both query_embedding and embedding_model to use already-indexed belief "
                "vectors. Treat hits as inspection candidates, not support, contradiction, "
                "or deduplication verdicts. "
                "Example: deepr_semantic_recall(expert_name='AI Strategy Expert', query='GPU deployment bottlenecks', top_k=5)"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                    "query": {"type": "string", "description": "Recall query"},
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum candidates to return",
                    },
                    "min_score": {
                        "type": "number",
                        "default": 0.0,
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Minimum recall score",
                    },
                    "domain": {"type": "string", "description": "Optional exact belief-domain filter"},
                    "query_embedding": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Explicit caller-supplied query embedding. Deepr does not generate it.",
                    },
                    "embedding_model": {
                        "type": "string",
                        "description": "Model label for already-indexed belief vectors",
                    },
                    "include_lexical_fallback": {
                        "type": "boolean",
                        "default": True,
                        "description": "Allow lexical candidates when vector hits are absent",
                    },
                },
                "required": ["expert_name", "query"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_expert_handoff",
            description=(
                "Return a versioned read-only handoff payload for an expert. Includes the "
                "stable schema version, profile summary, manifest counts, bounded claim and "
                "gap samples, dashboard telemetry, loop-status rollup, OKF interchange hints, "
                "and recommended follow-up MCP tools. Cost-$0 and does not mutate state. "
                "Use this as the first call when a downstream agent needs to consume an expert "
                "without relying on dashboard-specific response shapes. "
                "Example: deepr_expert_handoff(expert_name='AI Strategy Expert', max_claims=10)"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                    "max_claims": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Maximum top-confidence claims to include",
                    },
                    "max_gaps": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 0,
                        "maximum": 50,
                        "description": "Maximum top open gaps to include",
                    },
                    "loop_limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum loop runs to include in the rollup",
                    },
                    "include_claims": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include bounded claim samples",
                    },
                    "include_gaps": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include bounded open-gap samples",
                    },
                    "include_decisions": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include latest decision records",
                    },
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_route_gaps",
            description=(
                "Route an expert's top knowledge gaps to the best instrument to fill each: recon "
                "(infrastructure/email-security), distillr (academic/literature), primr (strategic "
                "company deep-dives), or general deep research (default). Read-only and cost-$0; "
                "returns per-gap instrument, whether it is installed, a cost estimate, and a "
                "rationale. Advisory - it recommends, it does not fill. "
                "Example: deepr_route_gaps(expert_name='AI Strategy Expert', top_n=5)"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                    "top_n": {"type": "integer", "default": 5, "description": "How many top gaps to route"},
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_what_changed",
            description=(
                "Perspective delta: what an expert's beliefs did since a timestamp - added, revised, "
                "contested (recorded with contradiction edges), or archived - each with its change "
                "reason and current snapshot. Read-only and cost-$0. Use this to re-sync with an "
                "expert you consulted before instead of re-reading everything. "
                "Example: deepr_what_changed(expert_name='AI Strategy Expert', since='2026-06-01T00:00:00+00:00')"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                    "since": {
                        "type": "string",
                        "description": "ISO 8601 timestamp; changes strictly after this moment are returned",
                    },
                },
                "required": ["expert_name", "since"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_contested",
            description=(
                "Open contradiction pairs in an expert's beliefs - both sides' claims, confidence, "
                "and provenance, plus whether each pair is open or dangling. Read-only and cost-$0. "
                "Surfaces live conflicts instead of a smoothed narrative; resolution stays with "
                "expert resolve-conflicts. Example: deepr_contested(expert_name='AI Strategy Expert')"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_explain_belief",
            description=(
                "Why the expert believes something: evidence roots (provenance), the confidence "
                "trajectory from the append-only event log, supporting/derived-from chains walked "
                "over the typed belief graph (depth-bounded), and any open contradictions. "
                "Read-only and cost-$0. The introspection query - use it to debug trust in a claim "
                "instead of taking the confidence number on faith. The belief argument is a belief "
                "id or claim text (fuzzy matched). "
                "Example: deepr_explain_belief(expert_name='AI Strategy Expert', belief='dynamic tool discovery')"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                    "belief": {"type": "string", "description": "Belief id or claim text to explain"},
                    "depth": {
                        "type": "integer",
                        "description": "Max hops along support chains (default 2, max 5)",
                    },
                },
                "required": ["expert_name", "belief"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_temporal_edges",
            description=(
                "Query temporal edge qualifiers in an expert's typed belief graph. Filters by valid_at "
                "(relationship valid at an instant), observed_since / observed_until (when the qualified "
                "relationship was observed), edge_type, and optional belief_ref. Read-only and cost-$0. "
                "Use when a host agent needs time-scoped belief relationships instead of all graph context. "
                "Example: deepr_temporal_edges(expert_name='AI Strategy Expert', valid_at='2026-06-15T00:00:00+00:00')"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert"},
                    "valid_at": {
                        "type": "string",
                        "description": "Optional ISO 8601 instant that must fall within edge valid_from/valid_until",
                    },
                    "observed_since": {
                        "type": "string",
                        "description": "Optional ISO 8601 lower bound for edge observed_at",
                    },
                    "observed_until": {
                        "type": "string",
                        "description": "Optional ISO 8601 upper bound for edge observed_at",
                    },
                    "edge_type": {
                        "type": "string",
                        "description": "Optional edge type: supports, contradicts, enables, or derived_from",
                    },
                    "belief_ref": {
                        "type": "string",
                        "description": "Optional belief id or claim text to restrict edges touching one belief",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 200,
                        "description": "Maximum matching edges to return",
                    },
                },
                "required": ["expert_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_reflect",
            description=(
                "Self-evaluate a completed research report before relying on or absorbing it. Scores "
                "the report against its question on grounding, completeness, calibration, and directness, "
                "and returns a verdict (accept / revise / re_research) with concrete issues and follow-up "
                "queries. Read-only; one small evaluation call. Use as a quality gate before acting on "
                "research. Example: deepr_reflect(report_id='<id>', depth=1)"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "report_id": {
                        "type": "string",
                        "description": "Job id of a completed report (as used with --context; see deepr search)",
                    },
                    "depth": {
                        "type": "integer",
                        "default": 1,
                        "description": "0 = skip, 1 = single pass, 2+ = rigorous (always proposes re-research)",
                    },
                },
                "required": ["report_id"],
            },
            category="experts",
            cost_tier="low",
        )
    )

    registry.register(
        ToolSchema(
            name="deepr_expert_absorb",
            description=(
                "Promote a completed research report into an expert's permanent beliefs "
                "(output-to-knowledge feedback loop). Extracts report-grounded claims, drops "
                "weak ones and any that contradict the expert's existing beliefs, then "
                "integrates the survivors as beliefs with the report id as provenance "
                "(deduped against existing beliefs). MUTATES the expert and runs one small "
                "extraction call (~$0.03); pass dry_run=true to preview without writing. "
                "Example: deepr_expert_absorb(expert_name='AI Strategy Expert', report_id='<id>', dry_run=true)"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {"type": "string", "description": "Name of the expert to absorb into"},
                    "report_id": {
                        "type": "string",
                        "description": "Job id of a completed research report (as used with --context; see deepr search). A job-id prefix also resolves.",
                    },
                    "min_confidence": {
                        "type": "number",
                        "default": 0.6,
                        "description": "Drop candidate claims the report supports more weakly than this",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": False,
                        "description": "Preview extracted/gated claims without writing any beliefs",
                    },
                },
                "required": ["expert_name", "report_id"],
            },
            category="experts",
            cost_tier="low",
        )
    )

    # Agentic tools
    registry.register(
        ToolSchema(
            name="deepr_agentic_research",
            description=(
                "Start autonomous multi-step research workflow with Plan-Execute-Review "
                "cycles. An expert autonomously decomposes goals, conducts research, and "
                "synthesizes findings. Costs $1-$10. Requires an existing expert. "
                "Always confirm budget with user before calling. "
                "Example: deepr_agentic_research(goal='Evaluate database options for "
                "our recommendation engine', expert_name='Tech Architect', budget=5.0)"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "High-level research goal. Be specific about the desired outcome.",
                    },
                    "expert_name": {
                        "type": "string",
                        "description": "Expert to use for reasoning (required). See deepr_list_experts.",
                    },
                    "budget": {"type": "number", "default": 5.0, "description": "Total budget for workflow ($1-$10)"},
                },
                "required": ["goal", "expert_name"],
            },
            category="agentic",
            cost_tier="high",
        )
    )

    return registry
