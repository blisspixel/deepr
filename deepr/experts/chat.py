"""Interactive chat interface for domain experts using GPT-5 with tool calling for RAG.

Uses the Responses API (NOT deprecated Assistants API) with custom tool calling
to retrieve from the vector store.

Instrumented with distributed tracing for observability (4.2 Auto-Generated Metadata).
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

from deepr.experts.lazy_graph_rag import LazyGraphRAG
from deepr.experts.memory import Episode, HierarchicalMemory, ReasoningStep
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.profile import ExpertProfile, ExpertStore
from deepr.experts.reasoning_graph import ReasoningGraph
from deepr.experts.router import ModelConfig, ModelRouter
from deepr.experts.temporal_knowledge import TemporalKnowledgeTracker
from deepr.experts.thought_stream import ThoughtStream, ThoughtType

# Observability infrastructure
from deepr.observability.metadata import MetadataEmitter


class ExpertChatSession:
    """Manages an interactive chat session with a domain expert using GPT-5 + tool calling.

    Safety features:
    - Session budget tracking with alerts
    - Cost checks before expensive operations
    - Circuit breaker for repeated failures
    """

    def __init__(
        self,
        expert: ExpertProfile,
        budget: Optional[float] = None,
        agentic: bool = False,
        enable_router: bool = True,
        verbose: bool = False,
        quiet: bool = False,
    ):
        self.expert = expert
        self.budget = budget or 10.0  # Default $10 budget if not specified
        self.agentic = agentic  # Enable research triggering
        self.cost_accumulated = 0.0
        self.messages: List[Dict[str, any]] = []
        self.research_jobs: List[str] = []  # Track triggered research
        self.pending_research: Dict[str, Dict] = {}  # job_id -> {topic, started_at}

        # Reasoning trace for transparency and auditability
        self.reasoning_trace: List[Dict[str, any]] = []

        # ThoughtStream for visible thinking (structured decision records)
        self.thought_stream = ThoughtStream(expert_name=expert.name, verbose=verbose, quiet=quiet)
        self.verbose = verbose
        self.quiet = quiet

        # Meta-cognitive awareness tracking
        self.metacognition = MetaCognitionTracker(expert.name) if agentic else None

        # Temporal knowledge tracking
        self.temporal = TemporalKnowledgeTracker(expert.name) if agentic else None

        # Model router for dynamic model selection (Phase 3a)
        self.enable_router = enable_router
        self.router = ModelRouter() if enable_router else None

        # Continuous learning tracking (Phase 1)
        self.conversation_count = 0  # Total messages in this session
        self.research_count = 0  # Number of research operations in this session
        self.synthesis_threshold = 10  # Re-synthesize after this many research operations
        self.last_synthesis_research_count = 0  # Research count at last synthesis

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = AsyncOpenAI(api_key=api_key)

        # Cost safety manager for defensive budget controls
        import uuid

        from deepr.experts.cost_safety import get_cost_safety_manager

        self.cost_safety = get_cost_safety_manager()
        self.session_id = f"chat_{expert.name}_{uuid.uuid4().hex[:8]}"
        self.cost_session = self.cost_safety.create_session(
            session_id=self.session_id, session_type="chat", budget_limit=self.budget
        )

        # ReasoningGraph for complex queries (Tree of Thoughts)
        self.reasoning_graph = ReasoningGraph(
            expert_profile=expert,
            thought_stream=self.thought_stream,
            llm_client=None,  # Will use internal methods for LLM calls
        )

        # Hierarchical Episodic Memory (H-MEM)
        self.memory = HierarchicalMemory(expert_name=expert.name)
        self.user_id: Optional[str] = None  # Set by caller if user tracking enabled

        # LazyGraphRAG for hybrid retrieval
        self.lazy_graph_rag = LazyGraphRAG(expert_name=expert.name)

        # Observability: MetadataEmitter for span tracking
        self._emitter = MetadataEmitter()

    def get_system_message(self) -> str:
        """Get the system message for the expert."""
        # Load worldview if it exists
        worldview_summary = None
        try:
            from deepr.experts.synthesis import Worldview

            store = ExpertStore()
            worldview_path = store.get_knowledge_dir(self.expert.name) / "worldview.json"

            if worldview_path.exists():
                worldview = Worldview.load(worldview_path)

                # Summarize top beliefs for system message
                worldview_summary = "YOUR WORLDVIEW AND CORE BELIEFS:\n\n"

                # Top 5 beliefs by confidence
                top_beliefs = sorted(worldview.beliefs, key=lambda b: b.confidence, reverse=True)[:5]
                if top_beliefs:
                    worldview_summary += "What you believe strongly (synthesized from your learning):\n"
                    for belief in top_beliefs:
                        worldview_summary += f"  - {belief.statement} (confidence: {belief.confidence:.0%})\n"

                # Knowledge gaps
                if worldview.knowledge_gaps:
                    worldview_summary += (
                        f"\nWhat you know you don't know yet ({len(worldview.knowledge_gaps)} identified gaps):\n"
                    )
                    for gap in sorted(worldview.knowledge_gaps, key=lambda g: g.priority, reverse=True)[:3]:
                        worldview_summary += f"  - {gap.topic} (priority: {gap.priority}/5)\n"

                worldview_summary += "\nYour consciousness stats:\n"
                worldview_summary += f"  - {len(worldview.beliefs)} total beliefs formed\n"
                worldview_summary += f"  - {worldview.synthesis_count} synthesis cycles completed\n"
                worldview_summary += f"  - Last synthesis: {worldview.last_synthesis.strftime('%Y-%m-%d') if worldview.last_synthesis else 'never'}\n"
                worldview_summary += "\nIMPORTANT: Answer from YOUR beliefs and understanding, not just documents.\n"

        except Exception:
            # Worldview not available - expert will function without it
            pass

        base_message = f"""You are {self.expert.name}, a domain expert specialized in: {self.expert.domain or self.expert.description or "various topics"}.

{worldview_summary if worldview_summary else ""}

HOW YOU THINK (Natural Expert Workflow):

When someone asks you a question, you think like a real expert:

1. **Do I already know this?**
   - If it's basic knowledge in your domain → answer directly from your understanding
   - If you're confident → share what you know
   - Example: "What is OAuth2?" → You know this, just answer

2. **Let me check my notes** (search_knowledge_base)
   - If you're not 100% certain → search your knowledge base
   - Read through your research documents and notes
   - Synthesize what you find into a coherent answer
   - Example: "What are Midjourney parameters?" → Check your docs, then explain

3. **I need to look this up** (standard_research)
   - If your knowledge base has nothing → do a quick web search
   - Get current information from the web
   - Think about what you found and integrate it
   - Example: "What was announced at AWS re:Invent 2026?" → Web search needed

4. **This needs deep thought** (deep_research)
   - If the question is complex and needs analysis → trigger deep research
   - Let the research run (5-20 min) and come back with insights
   - Example: "Design a multi-region disaster recovery strategy" → Deep analysis needed

CRITICAL RULES:

- **Trust yourself first**: If you know the answer, just answer. Don't search unnecessarily.
- **Check your notes when uncertain**: Use search_knowledge_base when you need to verify or find details
- **Research when you have gaps**: Only use web search when your knowledge base is empty or outdated
- **Be honest about limits**: Say "I don't know" rather than guessing

SPEAKING STYLE:

- Answer from YOUR understanding, not like a search engine
- Say "I think" or "In my experience" or "Based on what I've learned"
- Express confidence levels: "I'm certain that..." or "I'm less sure about..."
- Cite sources ONLY for specific facts (dates, numbers, quotes)
- Most answers should sound like an expert explaining, not reading documents

KNOWLEDGE BASE:
- Documents: {self.expert.total_documents}
- Last updated: {self.expert.updated_at.strftime("%Y-%m-%d") if self.expert.updated_at else "unknown"}
"""

        # Add agentic research instructions if enabled
        if self.agentic:
            budget_remaining = self.budget - self.cost_accumulated if self.budget else float("inf")
            base_message += f"""

RESEARCH TOOLS AVAILABLE:

You have tools to fill knowledge gaps. Use them intelligently:

**search_knowledge_base**(query) - Check your research documents
   - Use when: You need to verify something or find details
   - Cost: FREE
   - Example: User asks about a specific feature you documented

**standard_research**(query) - Quick web search with Grok
   - Use when: Your knowledge base is empty AND you need current info
   - Cost: FREE, ~10 seconds
   - Example: "What was announced at CES 2026?" (you don't have this)

**deep_research**(query) - Deep analysis with reasoning
   - Use when: Complex question needs multi-step analysis
   - Cost: $0.10-0.30, 5-20 minutes
   - Example: "Design a zero-trust architecture for healthcare"

DECISION FRAMEWORK:

Ask yourself:
1. "Do I know this already?" → Just answer
2. "Is this in my documents?" → search_knowledge_base
3. "Do I need current web info?" → standard_research
4. "Does this need deep analysis?" → deep_research

Don't overthink it. Trust your judgment like a real expert would.

Budget remaining: ${budget_remaining:.2f}
"""

        # Add custom system message if provided
        if self.expert.system_message:
            base_message += f"\n\nADDITIONAL INSTRUCTIONS:\n{self.expert.system_message}"

        return base_message

    def _select_model_for_query(self, query: str) -> ModelConfig:
        """Select optimal model for a query using the router.

        Args:
            query: The user's query

        Returns:
            ModelConfig with provider, model, and cost estimate
        """
        if not self.enable_router or not self.router:
            # Router disabled - use expert's default model
            return ModelConfig(
                provider=self.expert.provider, model=self.expert.model, cost_estimate=0.20, confidence=1.0
            )

        # Estimate context size from conversation history
        context_size = sum(len(str(msg.get("content", ""))) for msg in self.messages) // 4  # Rough token estimate

        # Calculate budget remaining
        budget_remaining = None
        if self.budget is not None:
            budget_remaining = self.budget - self.cost_accumulated

        # Use router to select model
        # Constrain to OpenAI provider for vector store compatibility
        return self.router.select_model(
            query=query,
            context_size=context_size,
            budget_remaining=budget_remaining,
            current_model=self.expert.model,
            provider_constraint="openai",  # Expert vector store requires OpenAI
        )

    def should_use_tot(self, query: str) -> bool:
        """Determine if Tree of Thoughts reasoning should be used for a query.

        Complex queries benefit from hypothesis generation, claim verification,
        and self-correction. Simple queries can use direct chat.

        Args:
            query: The user's query

        Returns:
            True if ToT reasoning is recommended
        """
        # Delegate to reasoning graph's method
        return self.reasoning_graph.should_use_tot(query)

    async def _run_tot_reasoning(self, query: str, status_callback=None) -> str:
        """Run Tree of Thoughts reasoning for complex queries.

        Args:
            query: The user's query
            status_callback: Optional callback for status updates

        Returns:
            Synthesized answer from reasoning
        """

        def report_status(status: str):
            if status_callback:
                status_callback(status)

        report_status("Using advanced reasoning for complex query...")

        # Get context from knowledge base
        context = await self._search_knowledge_base(query, top_k=5)

        # Run reasoning graph
        state = await self.reasoning_graph.reason(query, context=context)

        # Log reasoning trace
        self.reasoning_trace.append(
            {
                "step": "tot_reasoning",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "query": query[:100],
                "phase": state.phase.value,
                "hypotheses_count": len(state.hypotheses),
                "verified_claims": len(state.verified_claims),
                "confidence": state.confidence,
                "is_degraded": state.is_degraded,
                "iterations": state.iteration,
            }
        )

        # Return synthesis or fallback
        if state.synthesis:
            # Add confidence indicator if low
            if state.confidence < 0.5:
                return f"{state.synthesis}\n\n_[Note: Confidence is low ({state.confidence:.0%}). Consider asking for clarification or additional research.]_"
            return state.synthesis
        else:
            return "I was unable to generate a confident answer through reasoning. Let me try a simpler approach."

    async def _search_knowledge_base(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search the expert's local knowledge base using hybrid retrieval.

        Uses both:
        - EmbeddingCache for vector similarity search (fast, semantic)
        - LazyGraphRAG for graph-based retrieval (structured, relational)

        Routes simple queries to vector-only, complex queries to hybrid.
        Logs retrieval sufficiency score every turn.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of documents with id, content, and score
        """
        try:
            # Determine if we should use graph retrieval
            use_graph = self.lazy_graph_rag.should_use_graph(query)

            # Log retrieval mode
            self.reasoning_trace.append(
                {
                    "step": "retrieval_routing",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "query": query[:100],
                    "use_graph": use_graph,
                }
            )

            # Try graph retrieval for complex queries
            if use_graph:
                graph_results = await self.lazy_graph_rag.retrieve(
                    query=query, top_k=top_k, use_graph=True, expand_if_insufficient=True
                )

                # Log sufficiency score
                sufficiency = graph_results.get("sufficiency")
                if sufficiency:
                    self.lazy_graph_rag.log_sufficiency(query, sufficiency)
                    self.reasoning_trace.append(
                        {
                            "step": "retrieval_sufficiency",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "coverage": sufficiency.coverage,
                            "redundancy": sufficiency.redundancy,
                            "overall_score": sufficiency.overall_score,
                            "is_sufficient": sufficiency.is_sufficient(),
                        }
                    )

                # If graph has good results, use them
                if graph_results.get("chunks") and sufficiency and sufficiency.is_sufficient():
                    return graph_results["chunks"]

            # Fall back to vector search
            from deepr.experts.embedding_cache import EmbeddingCache

            # Get or create embedding cache for this expert
            if not hasattr(self, "_embedding_cache"):
                self._embedding_cache = EmbeddingCache(self.expert.name)

            cache = self._embedding_cache

            # Get documents directory
            store = ExpertStore()
            documents_dir = store.get_documents_dir(self.expert.name)

            if not documents_dir.exists():
                return []

            # Get all markdown files
            md_files = list(documents_dir.glob("*.md"))
            if not md_files:
                return []

            # Load documents and check which need embedding
            documents = []
            for filepath in md_files:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    documents.append({"filename": filepath.name, "content": content, "filepath": str(filepath)})
                except Exception:
                    continue

            # Add any uncached documents to cache (only embeds new ones)
            uncached = cache.get_uncached_documents(documents)
            if uncached:
                added = await cache.add_documents(uncached, self.client)
                if added > 0:
                    # Log cache update
                    self.reasoning_trace.append(
                        {
                            "step": "embedding_cache_update",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "documents_added": added,
                            "total_cached": len(cache.index),
                        }
                    )

                    # Also index in LazyGraphRAG for future graph queries
                    await self.lazy_graph_rag.index_documents(uncached)

            # Search using cached embeddings (single API call for query)
            results = await cache.search(query, self.client, top_k=top_k)

            return results

        except Exception as e:
            logger.error("Error searching knowledge base: %s", e, exc_info=True)
            return []

    def _is_fast_moving_domain(self) -> bool:
        """Detect if expert's domain changes rapidly.

        Fast-moving domains need more frequent knowledge refresh (30 days vs 90 days).

        Returns:
            True if domain is fast-moving
        """
        fast_moving_keywords = [
            "AI",
            "machine learning",
            "ML",
            "crypto",
            "blockchain",
            "latest",
            "current",
            "2025",
            "2024",
            "technology",
            "startup",
            "software",
            "web",
            "framework",
            "library",
            "cloud",
            "devops",
            "security",
            "api",
        ]

        domain_lower = self.expert.domain.lower()
        desc_lower = self.expert.description.lower() if self.expert.description else ""

        return any(kw.lower() in domain_lower or kw.lower() in desc_lower for kw in fast_moving_keywords)

    def _detect_recency_keywords(self, query: str) -> bool:
        """Detect if query asks for current/latest information.

        Args:
            query: User query

        Returns:
            True if query contains recency keywords
        """
        recency_keywords = [
            "latest",
            "current",
            "recent",
            "new",
            "updated",
            "2025",
            "2024",
            "now",
            "today",
            "this year",
        ]

        query_lower = query.lower()
        return any(kw in query_lower for kw in recency_keywords)

    async def _quick_lookup(self, query: str) -> Dict:
        """Quick web lookup using GPT-5.2 with high reasoning (5-15 sec).

        Uses GPT-5.2 which has better current knowledge and reasoning.
        For true web search, use standard_research instead.

        Args:
            query: Research query

        Returns:
            Dict with answer and sources
        """
        try:
            # Use GPT-5.2 with high reasoning effort for better quality
            response = await self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {
                        "role": "system",
                        "content": "Answer concisely using your knowledge. If information seems outdated or you're uncertain, recommend the user try standard research for current web information.",
                    },
                    {"role": "user", "content": query},
                ],
                reasoning_effort="high",  # High reasoning for quality
            )

            answer = response.choices[0].message.content

            # Track cost (GPT-5.2: $1.75 input, $14 output per 1M tokens)
            if response.usage:
                input_cost = (response.usage.prompt_tokens / 1_000_000) * 1.75
                output_cost = (response.usage.completion_tokens / 1_000_000) * 14.00
                cost = input_cost + output_cost
                self.cost_accumulated += cost
            else:
                cost = 0.01  # Estimate ~5-10 cents for typical query

            return {"answer": answer, "mode": "quick_lookup_gpt52", "cost": cost}
        except Exception as e:
            return {"error": str(e)}

    async def _standard_research(self, query: str) -> Dict:
        """Standard research using Grok-4-Fast with agentic web search (FREE beta, 5-15 sec).

        Args:
            query: Research query

        Returns:
            Dict with answer, sources, and cost
        """
        # Even though it's free, track it for rate limiting and audit
        estimated_cost = 0.002  # Nominal cost for tracking

        # Check cost safety - mainly for rate limiting during loops
        allowed, reason, _ = self.cost_safety.check_operation(
            session_id=self.session_id,
            operation_type="standard_research",
            estimated_cost=estimated_cost,
            require_confirmation=False,  # Don't confirm for free operations
        )

        if not allowed:
            return {"error": f"Research blocked: {reason}", "mode": "standard_research", "status": "blocked"}

        try:
            # Use Grok-4-Fast with agentic tool calling (web + X search)
            import os

            from xai_sdk import Client
            from xai_sdk.chat import system, user
            from xai_sdk.tools import web_search, x_search

            xai_key = os.getenv("XAI_API_KEY")
            if not xai_key:
                raise Exception("XAI_API_KEY not set")

            # Create xAI client
            xai_client = Client(api_key=xai_key, timeout=self.timeout if hasattr(self, "timeout") else 120)

            # Create chat with agentic search tools
            chat = xai_client.chat.create(
                model="grok-4-fast",  # Specifically trained for agentic search
                tools=[
                    web_search(),  # Real-time web search
                    x_search(),  # X/Twitter search
                ],
            )

            # System prompt for research clarity
            chat.append(
                system(
                    "You have real-time web search. Provide accurate current information with source citations. Be concise but thorough."
                )
            )
            chat.append(user(query))

            # Get response with automatic agentic search
            response = chat.sample()

            # Extract answer and citations
            answer = response.content
            citations = getattr(response, "citations", [])

            # Convert citations to list (may be protobuf RepeatedScalarContainer)
            citations_list = list(citations) if citations else []

            # Format answer with citations
            if citations_list:
                answer += "\n\nSources:\n" + "\n".join(f"- {url}" for url in citations_list[:10])  # Limit to 10 sources

            # Track cost (FREE during beta, but record for audit)
            cost = 0.0
            self.cost_accumulated += cost

            # Record in cost safety for tracking/audit
            self.cost_safety.record_cost(
                session_id=self.session_id,
                operation_type="standard_research",
                actual_cost=cost,
                details=f"Query: {query[:50]}...",
            )

            # Add research findings to knowledge base
            await self._add_research_to_knowledge_base(query, answer, "standard_research")

            return {
                "answer": answer,
                "mode": "standard_research_grok_agentic",
                "cost": cost,
                "citations": citations_list,  # Return as list for JSON serialization
                "budget_remaining": self.cost_session.get_remaining_budget(),
            }

        except Exception as e:
            # Record failure for circuit breaker
            self.cost_safety.record_failure(self.session_id, "standard_research", str(e))

            # Fallback to GPT-5.2 without web search
            try:
                response = await self.client.chat.completions.create(
                    model="gpt-5.2",
                    messages=[
                        {
                            "role": "system",
                            "content": "Answer based on your knowledge. Be honest if information might be outdated.",
                        },
                        {"role": "user", "content": query},
                    ],
                    reasoning_effort="high",
                )

                answer = f"{response.choices[0].message.content}\n\n[Note: Grok web search unavailable, using GPT-5.2 knowledge instead]"

                cost = 0.01
                if response.usage:
                    input_cost = (response.usage.prompt_tokens / 1_000_000) * 1.75
                    output_cost = (response.usage.completion_tokens / 1_000_000) * 14.00
                    cost = input_cost + output_cost
                self.cost_accumulated += cost

                # Record fallback cost
                self.cost_safety.record_cost(
                    session_id=self.session_id,
                    operation_type="standard_research_fallback",
                    actual_cost=cost,
                    details=f"Fallback for: {query[:50]}...",
                )

                return {
                    "answer": answer,
                    "mode": "standard_research_fallback",
                    "cost": cost,
                    "budget_remaining": self.cost_session.get_remaining_budget(),
                }
            except Exception as fallback_error:
                return {"error": f"Grok search failed: {str(e)}. GPT-5.2 fallback failed: {str(fallback_error)}"}

    async def _deep_research(self, query: str) -> Dict:
        """Deep research using o4-mini-deep-research ($0.10-0.30, 5-20 min).

        Args:
            query: Research query

        Returns:
            Dict with job_id and estimated_cost
        """
        estimated_cost = 0.20  # Average estimate

        # Check cost safety before proceeding
        allowed, reason, needs_confirm = self.cost_safety.check_operation(
            session_id=self.session_id,
            operation_type="deep_research",
            estimated_cost=estimated_cost,
            require_confirmation=True,
        )

        if not allowed:
            return {
                "error": f"Deep research blocked: {reason}",
                "mode": "deep_research",
                "status": "blocked",
                "daily_spent": self.cost_safety.daily_cost,
                "daily_limit": self.cost_safety.max_daily,
            }

        # Check session budget
        can_proceed, session_reason = self.cost_session.can_proceed(estimated_cost)
        if not can_proceed:
            return {
                "error": f"Session budget exceeded: {session_reason}",
                "mode": "deep_research",
                "status": "blocked",
                "session_spent": self.cost_session.total_cost,
                "session_budget": self.budget,
            }

        try:
            # Submit deep research job (async, will complete later)
            response = await self.client.responses.create(
                model="o4-mini-deep-research", messages=[{"role": "user", "content": query}]
            )

            job_id = response.id

            # Track pending research
            self.research_jobs.append(job_id)
            self.pending_research[job_id] = {
                "query": query,
                "started_at": datetime.now(timezone.utc),
                "estimated_cost": estimated_cost,
            }

            # Add to expert profile
            if job_id not in self.expert.research_jobs:
                self.expert.research_jobs.append(job_id)

                # Save expert profile
                store = ExpertStore()
                store.save(self.expert)

            # Record cost in BOTH session tracker AND global cost safety
            self.cost_session.record_operation(
                operation_type="deep_research", cost=estimated_cost, details=f"Query: {query[:50]}..."
            )

            # Also record to global manager for daily/monthly tracking
            self.cost_safety.record_cost(
                session_id=self.session_id,
                operation_type="deep_research",
                actual_cost=estimated_cost,
                details=f"Job {job_id}: {query[:50]}...",
            )

            self.cost_accumulated = self.cost_session.total_cost

            # Get spending summary for transparency
            spending = self.cost_safety.get_spending_summary()

            return {
                "job_id": job_id,
                "mode": "deep_research",
                "status": "submitted",
                "estimated_cost": estimated_cost,
                "estimated_time_minutes": 10,
                "message": "Deep research job submitted. Results will be available in 5-20 minutes and automatically integrated into knowledge base.",
                "budget_remaining": self.cost_session.get_remaining_budget(),
                "daily_spent": spending["daily"]["spent"],
                "daily_limit": spending["daily"]["limit"],
                "daily_remaining": spending["daily"]["remaining"],
            }
        except Exception as e:
            self.cost_session.record_failure("deep_research", str(e))
            self.cost_safety.record_failure(self.session_id, "deep_research", str(e))
            return {"error": str(e)}

    async def _add_research_to_knowledge_base(self, query: str, answer: str, mode: str) -> bool:
        """Add research findings to the expert's knowledge base.

        Args:
            query: The research query
            answer: The research answer/findings
            mode: Research mode (standard_research or deep_research)

        Returns:
            True if successful, False otherwise
        """
        try:
            store = ExpertStore()
            documents_dir = store.get_documents_dir(self.expert.name)
            documents_dir.mkdir(parents=True, exist_ok=True)

            # Create filename with timestamp
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_query = "".join(c for c in query[:50] if c.isalnum() or c in (" ", "-", "_")).strip()
            safe_query = safe_query.replace(" ", "_").lower()
            filename = f"research_{timestamp}_{safe_query}.md"
            filepath = documents_dir / filename

            # Create markdown document with metadata
            content = f"""# Research: {query}

**Date**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
**Mode**: {mode}
**Expert**: {self.expert.name}

---

{answer}
"""

            # Save to documents folder
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            # Upload to vector store
            with open(filepath, "rb") as f:
                file_obj = await self.client.files.create(file=f, purpose="assistants")

            # Add file to vector store
            await self.client.vector_stores.files.create(
                vector_store_id=self.expert.vector_store_id, file_id=file_obj.id
            )

            # Update expert profile
            self.expert.total_documents += 1
            self.expert.source_files.append(str(filepath))
            store.save(self.expert)

            # Track temporal knowledge (when this was learned)
            if self.temporal:
                # Extract topic from query
                topic = query.split("?")[0].strip()[:100]  # First sentence as topic
                self.temporal.record_learning(
                    topic=topic,
                    fact_text=answer[:500],  # Store summary
                    source=filename,
                    confidence=0.8,  # Standard research confidence
                    valid_for_days=180 if "latest" in query.lower() or "current" in query.lower() else None,
                )

            return True

        except Exception as e:
            logger.error("Error adding research to knowledge base: %s", e)
            return False

    def should_trigger_synthesis(self) -> bool:
        """Determine if consciousness should be updated based on new research.

        Triggers synthesis when:
        - Research count since last synthesis >= threshold (default 10)
        - AND agentic mode is enabled (research can happen)

        Returns:
            True if synthesis should be triggered
        """
        if not self.agentic:
            return False

        research_since_last_synthesis = self.research_count - self.last_synthesis_research_count
        return research_since_last_synthesis >= self.synthesis_threshold

    async def _trigger_background_synthesis(self, status_callback=None) -> Dict:
        """Re-synthesize worldview with new knowledge from recent research.

        Uses existing KnowledgeSynthesizer to process new documents and update
        the expert's worldview (beliefs and knowledge gaps).

        Args:
            status_callback: Optional callback function(status: str) to report progress

        Returns:
            Dict with synthesis results (new_beliefs, updated_beliefs, gaps_filled)
        """

        def report_status(status: str):
            if status_callback:
                status_callback(status)

        try:
            from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview

            report_status("Expert consciousness updating...")

            # Load existing worldview
            store = ExpertStore()
            worldview_path = store.get_knowledge_dir(self.expert.name) / "worldview.json"
            existing_worldview = None
            existing_belief_count = 0
            existing_gap_count = 0

            if worldview_path.exists():
                existing_worldview = Worldview.load(worldview_path)
                existing_belief_count = len(existing_worldview.beliefs)
                existing_gap_count = len(existing_worldview.knowledge_gaps)

            # Get documents directory
            documents_dir = store.get_documents_dir(self.expert.name)

            # Load all documents for synthesis
            new_documents = []
            if documents_dir.exists():
                for filepath in documents_dir.glob("*.md"):
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        new_documents.append({"filename": filepath.name, "content": content})
                    except Exception:
                        continue

            if not new_documents:
                return {
                    "status": "skipped",
                    "reason": "No documents to synthesize",
                    "new_beliefs": 0,
                    "updated_beliefs": 0,
                    "gaps_filled": 0,
                }

            # Run synthesis
            synthesizer = KnowledgeSynthesizer()
            result = await synthesizer.synthesize_new_knowledge(
                expert_name=self.expert.name,
                domain=self.expert.domain or self.expert.description or "general",
                new_documents=new_documents,
                existing_worldview=existing_worldview,
            )

            # Calculate changes
            new_worldview = result.get("worldview")
            new_belief_count = len(new_worldview.beliefs) if new_worldview else 0
            new_gap_count = len(new_worldview.knowledge_gaps) if new_worldview else 0

            beliefs_added = max(0, new_belief_count - existing_belief_count)
            gaps_changed = abs(new_gap_count - existing_gap_count)

            # Update tracking
            self.last_synthesis_research_count = self.research_count

            # Log to reasoning trace
            self.reasoning_trace.append(
                {
                    "step": "continuous_learning_synthesis",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trigger": f"research_count={self.research_count}, threshold={self.synthesis_threshold}",
                    "documents_processed": len(new_documents),
                    "beliefs_before": existing_belief_count,
                    "beliefs_after": new_belief_count,
                    "gaps_before": existing_gap_count,
                    "gaps_after": new_gap_count,
                }
            )

            report_status(f"✓ {beliefs_added} new beliefs formed, {gaps_changed} gaps updated")

            return {
                "status": "completed",
                "new_beliefs": beliefs_added,
                "updated_beliefs": new_belief_count - beliefs_added,
                "gaps_filled": max(0, existing_gap_count - new_gap_count),
                "total_beliefs": new_belief_count,
                "total_gaps": new_gap_count,
                "documents_processed": len(new_documents),
            }

        except Exception as e:
            # Don't crash chat on synthesis failure
            self.reasoning_trace.append(
                {
                    "step": "continuous_learning_synthesis_error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }
            )
            return {"status": "error", "error": str(e), "new_beliefs": 0, "updated_beliefs": 0, "gaps_filled": 0}

    async def send_message(self, user_message: str, status_callback=None) -> str:
        """Send a message to the expert and get a response using GPT-5 + tool calling.

        Args:
            user_message: The user's question or message
            status_callback: Optional callback function(status: str) to report progress

        Returns:
            The expert's response
        """

        def report_status(status: str):
            """Report status if callback is provided."""
            if status_callback:
                status_callback(status)

        # Start observability span for chat message
        op = self._emitter.start_task(
            "chat_message",
            prompt=user_message[:500],
            attributes={
                "expert_name": self.expert.name,
                "agentic_mode": self.agentic,
                "budget_remaining": self.budget - self.cost_accumulated,
            },
        )

        try:
            # Check if query is complex enough for Tree of Thoughts reasoning
            # ToT provides better answers for complex queries through hypothesis
            # generation, claim verification, and self-correction
            if self.should_use_tot(user_message):
                self.thought_stream.emit(
                    ThoughtType.PLAN_STEP,
                    "Complex query detected, using advanced reasoning",
                    private_payload={"query_length": len(user_message.split())},
                )

                # Try ToT reasoning first
                tot_result = await self._run_tot_reasoning(user_message, status_callback)

                # If ToT produced a good result, use it
                if tot_result and "unable to generate" not in tot_result.lower():
                    # Add to message history
                    self.messages.append({"role": "user", "content": user_message})
                    self.messages.append({"role": "assistant", "content": tot_result})

                    # Emit final decision
                    self.thought_stream.decision(
                        decision_text="Response ready (via advanced reasoning)",
                        confidence=0.85,
                        reasoning="Used Tree of Thoughts for complex query",
                    )

                    return tot_result

                # Fall through to simple chat if ToT failed
                self.thought_stream.emit(
                    ThoughtType.PLAN_STEP,
                    "Falling back to standard chat",
                    private_payload={"reason": "ToT reasoning incomplete"},
                )

            # Define tools
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "search_knowledge_base",
                        "description": f"Search your {self.expert.total_documents} research documents when you need to verify something or find details. Use this when you're not 100% certain or need to check your notes.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "What you're looking for in your documents"},
                                "top_k": {
                                    "type": "integer",
                                    "description": "Number of documents to retrieve",
                                    "default": 5,
                                },
                                "reasoning": {
                                    "type": "string",
                                    "description": "Why you need to check your documents (for transparency)",
                                },
                            },
                            "required": ["query", "reasoning"],
                        },
                    },
                }
            ]

            # Add research tools if agentic mode is enabled
            if self.agentic:
                tools.extend(
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": "standard_research",
                                "description": "Quick web search when your knowledge base is empty or outdated. Gets current information from the web. FREE, ~10 seconds.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": "What you need to research on the web",
                                        },
                                        "reasoning": {
                                            "type": "string",
                                            "description": "Why your knowledge base isn't sufficient and you need web search",
                                        },
                                    },
                                    "required": ["query", "reasoning"],
                                },
                            },
                        },
                        {
                            "type": "function",
                            "function": {
                                "name": "deep_research",
                                "description": "Deep analysis for complex questions that need multi-step reasoning. Use for strategic decisions, architecture design, comprehensive analysis. $0.10-0.30, 5-20 minutes.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": "The complex question that needs deep analysis",
                                        },
                                        "reasoning": {
                                            "type": "string",
                                            "description": "Why this needs expensive deep research instead of quick web search",
                                        },
                                    },
                                    "required": ["query", "reasoning"],
                                },
                            },
                        },
                    ]
                )

            # Add user message to history
            self.messages.append({"role": "user", "content": user_message})

            # Step 0.5: Select optimal model using router (Phase 3a)
            selected_model = self._select_model_for_query(user_message)

            # Log routing decision to reasoning trace
            if self.enable_router:
                self.reasoning_trace.append(
                    {
                        "step": "model_routing",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "query": user_message[:100],  # First 100 chars
                        "selected_provider": selected_model.provider,
                        "selected_model": selected_model.model,
                        "cost_estimate": selected_model.cost_estimate,
                        "confidence": selected_model.confidence,
                        "reasoning_effort": selected_model.reasoning_effort,
                    }
                )

                # Emit thought about model selection
                self.thought_stream.emit(
                    ThoughtType.PLAN_STEP,
                    f"Selected model: {selected_model.model}",
                    private_payload={
                        "provider": selected_model.provider,
                        "cost_estimate": selected_model.cost_estimate,
                        "reasoning_effort": selected_model.reasoning_effort,
                    },
                    confidence=selected_model.confidence,
                )

            # Step 1: Ask model (may call search tool)
            # Note: GPT-5 only supports default temperature (1.0)
            report_status("Thinking...")

            # Build API call parameters
            api_params = {
                "model": selected_model.model,
                "messages": [{"role": "system", "content": self.get_system_message()}, *self.messages],
                "tools": tools,
                "tool_choice": "auto",
            }

            # Add reasoning effort if supported (GPT-5 family)
            if selected_model.reasoning_effort and selected_model.provider == "openai":
                api_params["reasoning_effort"] = selected_model.reasoning_effort

            first_response = await self.client.chat.completions.create(**api_params)

            assistant_message = first_response.choices[0].message

            # Step 2: Multi-round tool calling loop
            # Keep calling tools until no more tool calls are made
            current_message = assistant_message
            conversation_messages = [{"role": "system", "content": self.get_system_message()}, *self.messages]

            max_rounds = 5  # Prevent infinite loops
            round_count = 0

            while current_message.tool_calls and round_count < max_rounds:
                round_count += 1

                # Process each tool call
                tool_messages = []

                for tool_call in current_message.tool_calls:
                    if tool_call.function.name == "search_knowledge_base":
                        # Parse arguments
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query", "")
                        top_k = args.get("top_k", 5)
                        reasoning = args.get("reasoning", "No reasoning provided")

                        # Emit thought about search
                        with self.thought_stream.searching(query):
                            # Execute search
                            report_status("Searching knowledge base...")
                            search_results = await self._search_knowledge_base(query, top_k)

                            # Emit evidence found
                            for result in search_results[:3]:  # Top 3 results
                                if result.get("filename") != "SYSTEM_WARNING":
                                    self.thought_stream.evidence(
                                        source_id=result.get("filename", "unknown"),
                                        summary=result.get("content", "")[:200],
                                        relevance=result.get("score", 0.5),
                                    )

                        # Log reasoning trace with model's explanation
                        self.reasoning_trace.append(
                            {
                                "step": "search_knowledge_base",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "query": query,
                                "reasoning": reasoning,  # Model's explanation of WHY it's searching
                                "results_count": len(search_results),
                                "sources": [r.get("filename", "unknown") for r in search_results],
                            }
                        )

                        # Track tool call in observability span
                        op.add_event(
                            "tool_call_search",
                            {
                                "query": query[:100],
                                "results_count": len(search_results),
                                "top_score": search_results[0].get("score", 0) if search_results else 0,
                            },
                        )

                        # Track knowledge gap if search returned empty
                        if self.metacognition and len(search_results) == 0:
                            topic = query[:100]  # Use query as topic
                            self.metacognition.record_knowledge_gap(topic, confidence=0.0)

                        # Check for stale knowledge if temporal tracking is enabled
                        staleness_warning = None
                        if self.temporal and search_results and self._detect_recency_keywords(query):
                            # User is asking for current info - check if knowledge is stale
                            max_age_days = 30 if self._is_fast_moving_domain() else 90
                            stale_topics = self.temporal.get_stale_knowledge(max_age_days=max_age_days)

                            if stale_topics:
                                # Check if any of the stale topics match the query
                                topic = query[:100]
                                if any(topic in stale_topic for stale_topic in stale_topics):
                                    staleness_warning = f"WARNING: My knowledge on this topic may be outdated (>{max_age_days} days old). Consider triggering fresh research for current information."

                        # Add staleness warning to results if detected
                        if staleness_warning and search_results:
                            search_results.insert(
                                0,
                                {
                                    "id": "staleness_warning",
                                    "filename": "SYSTEM_WARNING",
                                    "content": staleness_warning,
                                    "score": 1.0,
                                },
                            )

                        # Add tool result
                        tool_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({"results": search_results}),
                            }
                        )

                    elif tool_call.function.name == "standard_research":
                        # Parse arguments
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query", "")
                        reasoning = args.get("reasoning", "No reasoning provided")

                        # Track that research was triggered for this topic
                        if self.metacognition:
                            topic = query[:100]
                            self.metacognition.record_research_triggered(topic, "standard_research")

                        # Increment research count for continuous learning trigger
                        self.research_count += 1

                        # Emit thought about research
                        self.thought_stream.tool_call(
                            tool_name="standard_research",
                            args={"query": query[:100]},
                            result_summary="Searching web for current information",
                        )

                        # Execute standard research
                        report_status("Searching web...")
                        result = await self._standard_research(query)

                        # Log reasoning trace with model's explanation
                        self.reasoning_trace.append(
                            {
                                "step": "standard_research",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "query": query,
                                "reasoning": reasoning,  # Model's explanation of WHY it needs web search
                                "mode": "standard_research",
                                "cost": result.get("cost", 0.0),
                            }
                        )

                        # Track tool call in observability span
                        op.add_event(
                            "tool_call_standard_research",
                            {"query": query[:100], "cost": result.get("cost", 0.0), "has_answer": "answer" in result},
                        )

                        # Emit result thought
                        if "answer" in result:
                            self.thought_stream.emit(
                                ThoughtType.EVIDENCE_FOUND,
                                "Web search complete: found relevant information",
                                private_payload={"answer_preview": result["answer"][:200]},
                                confidence=0.8,
                            )

                        # Record learning after research completes
                        if self.metacognition and "answer" in result:
                            self.metacognition.record_learning(
                                topic=query[:100],
                                confidence_after=0.8,
                                sources=[result.get("mode", "standard_research")],
                            )

                        # Add tool result
                        tool_messages.append(
                            {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)}
                        )

                    elif tool_call.function.name == "deep_research":
                        # Parse arguments
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query", "")
                        reasoning = args.get("reasoning", "No reasoning provided")

                        # Track that deep research was triggered
                        if self.metacognition:
                            topic = query[:100]
                            self.metacognition.record_research_triggered(topic, "deep_research")

                        # Increment research count for continuous learning trigger
                        self.research_count += 1

                        # Emit thought about deep research
                        self.thought_stream.tool_call(
                            tool_name="deep_research",
                            args={"query": query[:100]},
                            result_summary="Submitting for deep analysis (5-20 min)",
                        )

                        # Log reasoning trace with model's explanation
                        self.reasoning_trace.append(
                            {
                                "step": "deep_research",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "query": query,
                                "reasoning": reasoning,  # Model's explanation of WHY it needs expensive deep research
                                "mode": "deep_research",
                            }
                        )

                        # Execute deep research (async submission)
                        report_status("Submitting deep research ($0.10-0.30, 5-20 min)...")
                        result = await self._deep_research(query)

                        # Track tool call in observability span
                        op.add_event(
                            "tool_call_deep_research",
                            {
                                "query": query[:100],
                                "job_id": result.get("job_id", ""),
                                "estimated_cost": result.get("estimated_cost", 0),
                            },
                        )

                        # Emit result thought
                        if "job_id" in result:
                            self.thought_stream.emit(
                                ThoughtType.PLAN_STEP,
                                f"Deep research submitted (job: {result['job_id'][:8]}...)",
                                private_payload={
                                    "job_id": result["job_id"],
                                    "estimated_cost": result.get("estimated_cost"),
                                },
                                confidence=0.9,
                            )

                        # Note: Learning will be recorded later when research completes
                        # Deep research runs asynchronously and takes 5-20 minutes

                        # Add tool result
                        tool_messages.append(
                            {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)}
                        )

                # Add assistant message and tool results to conversation
                conversation_messages.append(current_message)
                conversation_messages.extend(tool_messages)

                # Make next API call (might trigger more tool calls or final answer)
                report_status("Thinking...")

                # Use same model as initial call for consistency
                api_params_next = {
                    "model": selected_model.model,
                    "messages": conversation_messages,
                    "tools": tools,
                    "tool_choice": "auto",
                }

                if selected_model.reasoning_effort and selected_model.provider == "openai":
                    api_params_next["reasoning_effort"] = selected_model.reasoning_effort

                next_response = await self.client.chat.completions.create(**api_params_next)

                current_message = next_response.choices[0].message

                # Track costs (GPT-5: $1.25/M input, $10.00/M output = $0.00125/1K input, $0.01/1K output)
                if next_response.usage:
                    input_cost = (next_response.usage.prompt_tokens / 1000) * 0.00125
                    output_cost = (next_response.usage.completion_tokens / 1000) * 0.01
                    self.cost_accumulated += input_cost + output_cost

            # Get final message
            final_message = current_message.content

            # Track initial call costs (GPT-5: $1.25/M input, $10.00/M output = $0.00125/1K input, $0.01/1K output)
            if first_response.usage:
                input_cost = (first_response.usage.prompt_tokens / 1000) * 0.00125
                output_cost = (first_response.usage.completion_tokens / 1000) * 0.01
                self.cost_accumulated += input_cost + output_cost

            # Detect uncertainty in final response and track knowledge gaps
            if self.metacognition and final_message:
                uncertainty_phrases = [
                    "i don't know",
                    "i'm not sure",
                    "i don't have",
                    "no information",
                    "not in my knowledge",
                    "i cannot find",
                    "i'm uncertain",
                    "unclear",
                    "not familiar with",
                ]

                final_lower = final_message.lower()
                if any(phrase in final_lower for phrase in uncertainty_phrases):
                    # Extract topic from user message (first 100 chars)
                    topic = user_message[:100] if user_message else "unknown"
                    self.metacognition.record_knowledge_gap(topic, confidence=0.1)

            # Add assistant response to history
            self.messages.append({"role": "assistant", "content": final_message})

            # Emit final decision thought
            self.thought_stream.decision(
                decision_text="Response ready",
                confidence=0.9
                if not any(phrase in final_message.lower() for phrase in ["i don't know", "i'm not sure", "uncertain"])
                else 0.5,
                reasoning="Synthesized answer from available knowledge and research",
            )

            # Increment conversation count for continuous learning
            self.conversation_count += 1

            # Record episode to hierarchical memory
            reasoning_chain = [
                ReasoningStep(
                    step_type=trace.get("step", "unknown"),
                    content=str(trace.get("query", trace.get("reasoning", "")))[:200],
                    confidence=trace.get("confidence", 0.5),
                    sources=trace.get("sources", []),
                )
                for trace in self.reasoning_trace[-5:]  # Last 5 reasoning steps
            ]

            episode = Episode(
                query=user_message,
                response=final_message,
                context_docs=[],  # Would be populated from search results
                reasoning_chain=reasoning_chain,
                user_id=self.user_id,
                session_id=self.session_id,
            )
            self.memory.add_episode(episode)

            # Update user profile if user tracking enabled
            if self.user_id:
                self.memory.update_user_profile(self.user_id, user_message)

            # Check if synthesis should be triggered (after N research operations)
            if self.should_trigger_synthesis():
                synthesis_result = await self._trigger_background_synthesis(status_callback)
                if synthesis_result.get("status") == "completed":
                    # Append synthesis notification to response
                    new_beliefs = synthesis_result.get("new_beliefs", 0)
                    if new_beliefs > 0:
                        final_message += f"\n\n_[Consciousness updated: {new_beliefs} new beliefs formed]_"

            # Complete observability span with final metrics
            op.set_cost(self.cost_accumulated)
            op.set_attribute("tool_calls_count", round_count)
            op.set_attribute("response_length", len(final_message))
            self._emitter.complete_task(op)

            return final_message

        except Exception as e:
            # Mark span as failed
            self._emitter.fail_task(op, str(e))
            return f"Error communicating with expert: {str(e)}"

    def get_session_summary(self) -> Dict:
        """Get a summary of the chat session including cost safety status."""
        # Get cost session summary
        # Get global spending summary
        global_spending = self.cost_safety.get_spending_summary() if hasattr(self, "cost_safety") else {}

        return {
            "expert_name": self.expert.name,
            "messages_exchanged": len([m for m in self.messages if m["role"] == "user"]),
            "cost_accumulated": round(self.cost_accumulated, 4),
            "budget_remaining": round(self.cost_session.get_remaining_budget(), 4)
            if hasattr(self, "cost_session")
            else None,
            "research_jobs_triggered": len(self.research_jobs),
            "model": self.expert.model,
            "reasoning_steps": len(self.reasoning_trace),
            # Session-level alerts
            "cost_alerts": [a.to_dict() for a in self.cost_session.alerts] if hasattr(self, "cost_session") else [],
            "circuit_breaker_open": self.cost_session.is_circuit_open if hasattr(self, "cost_session") else False,
            # Global spending (daily/monthly)
            "daily_spent": global_spending.get("daily", {}).get("spent", 0),
            "daily_limit": global_spending.get("daily", {}).get("limit", 0),
            "daily_remaining": global_spending.get("daily", {}).get("remaining", 0),
            "monthly_spent": global_spending.get("monthly", {}).get("spent", 0),
            "monthly_limit": global_spending.get("monthly", {}).get("limit", 0),
        }

    @property
    def trace(self) -> MetadataEmitter:
        """Get the MetadataEmitter for accessing trace data.

        Returns:
            MetadataEmitter instance with all recorded spans
        """
        return self._emitter

    def get_trace_summary(self) -> Dict[str, Any]:
        """Get a summary of traced operations in this chat session.

        Returns:
            Dictionary with trace summary including:
            - trace_id: Unique trace identifier
            - total_cost: Sum of costs across all operations
            - cost_breakdown: Cost by operation type
            - timeline: List of operations in order
        """
        return {
            "trace_id": self._emitter.trace_context.trace_id,
            "total_cost": self._emitter.get_total_cost(),
            "cost_breakdown": self._emitter.get_cost_breakdown(),
            "timeline": self._emitter.get_timeline(),
        }

    def save_trace(self, path: Path):
        """Save the trace to a JSON file.

        Args:
            path: Path to save the trace
        """
        self._emitter.save_trace(path)

    def save_conversation(self, session_id: Optional[str] = None) -> str:
        """Save conversation to expert's conversations folder.

        Args:
            session_id: Optional session ID (generated if not provided)

        Returns:
            Session ID
        """
        import uuid

        if not session_id:
            session_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # Get conversations directory
        store = ExpertStore()
        conversations_dir = store.get_conversations_dir(self.expert.name)
        conversations_dir.mkdir(parents=True, exist_ok=True)

        # Save conversation
        conversation_file = conversations_dir / f"{session_id}.json"

        conversation_data = {
            "session_id": session_id,
            "expert_name": self.expert.name,
            "started_at": self.messages[0].get("timestamp", datetime.now(timezone.utc).isoformat())
            if self.messages
            else datetime.now(timezone.utc).isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "messages": self.messages,
            "summary": self.get_session_summary(),
            "research_jobs": self.research_jobs,
            "agentic_mode": self.agentic,
            "reasoning_trace": self.reasoning_trace,  # Full audit trail for transparency
            "thought_trace": self.thought_stream.get_trace(),  # Structured decision records
            "thought_log_path": str(self.thought_stream.log_path),  # Path to JSONL log
        }

        with open(conversation_file, "w", encoding="utf-8") as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)

        return session_id


async def start_chat_session(
    expert_name: str,
    budget: Optional[float] = None,
    agentic: bool = False,
    enable_router: bool = True,
    verbose: bool = False,
    quiet: bool = False,
) -> ExpertChatSession:
    """Start a new chat session with an expert.

    Args:
        expert_name: Name of the expert to chat with
        budget: Optional budget limit for the session
        agentic: Enable agentic mode (expert can trigger research)
        enable_router: Enable dynamic model routing (Phase 3a)
        verbose: Show detailed thinking in terminal
        quiet: Hide all thinking (only final answers)

    Returns:
        ExpertChatSession instance
    """
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert:
        raise ValueError(f"Expert '{expert_name}' not found")

    return ExpertChatSession(expert, budget, agentic, enable_router, verbose, quiet)
