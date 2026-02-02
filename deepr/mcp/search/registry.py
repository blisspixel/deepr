"""
Tool Registry with BM25/semantic search for dynamic tool discovery.

This module maintains a searchable index of all Deepr tools, enabling
the gateway pattern that reduces initial context by ~85%.
"""

from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class ToolSchema:
    """Schema for a single MCP tool."""
    name: str
    description: str
    input_schema: dict
    category: str = "general"
    cost_tier: str = "free"  # free, low, medium, high
    
    _tokens: list[str] = field(default_factory=list, repr=False)
    
    def __post_init__(self):
        """Tokenize description for search indexing."""
        if not self._tokens:
            self._tokens = self._tokenize(f"{self.name} {self.description} {self.category}")
    
    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple tokenization for BM25 indexing."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        return [t for t in text.split() if len(t) > 2]
    
    @property
    def tokens(self) -> list[str]:
        return self._tokens
    
    def to_mcp_format(self) -> dict:
        """Convert to MCP tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema
        }


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
    
    def __init__(self):
        self._tools: dict[str, ToolSchema] = {}
        self._index: Optional[BM25Index] = None
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
    
    def get(self, name: str) -> Optional[ToolSchema]:
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
            (self._tools[name], scores[idx])
            for idx, name in enumerate(self._tool_order)
            if name in self._tools
        ]
        
        # Sort by score descending, filter zero scores
        ranked = sorted(
            [(t, s) for t, s in tool_scores if s > 0],
            key=lambda x: x[1],
            reverse=True
        )
        
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
        
        corpus = [
            self._tools[name].tokens
            for name in self._tool_order
            if name in self._tools
        ]
        
        self._index = BM25Index()
        self._index.fit(corpus)
    
    def estimate_tokens(self, tools: Optional[list[ToolSchema]] = None) -> int:
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
    
    # Research tools
    registry.register(ToolSchema(
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
    ))

    registry.register(ToolSchema(
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
    ))

    registry.register(ToolSchema(
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
    ))

    # Expert tools
    registry.register(ToolSchema(
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
    ))

    registry.register(ToolSchema(
        name="deepr_query_expert",
        description=(
            "Query a domain expert with a question. Expert answers from their "
            "knowledge base with citations and confidence levels. For questions "
            "outside the expert's knowledge, enable agentic=true to let the expert "
            "trigger new research. Do NOT use for current events or news."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "expert_name": {"type": "string", "description": "Name of the expert (from deepr_list_experts)"},
                "question": {"type": "string", "description": "Question to ask the expert"},
                "agentic": {"type": "boolean", "default": False, "description": "Enable autonomous research if expert lacks knowledge"},
                "budget": {"type": "number", "default": 0.0, "description": "Budget for agentic research (only used if agentic=true)"},
            },
            "required": ["expert_name", "question"],
        },
        category="experts",
        cost_tier="low",
    ))

    registry.register(ToolSchema(
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
    ))

    # Agentic tools
    registry.register(ToolSchema(
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
                "goal": {"type": "string", "description": "High-level research goal. Be specific about the desired outcome."},
                "expert_name": {"type": "string", "description": "Expert to use for reasoning (required). See deepr_list_experts."},
                "budget": {"type": "number", "default": 5.0, "description": "Total budget for workflow ($1-$10)"},
            },
            "required": ["goal"],
        },
        category="agentic",
        cost_tier="high",
    ))
    
    return registry
