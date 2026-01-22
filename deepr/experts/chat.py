"""Interactive chat interface for domain experts using GPT-5 with tool calling for RAG.

Uses the Responses API (NOT deprecated Assistants API) with custom tool calling
to retrieve from the vector store.
"""

import os
import json
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
from openai import AsyncOpenAI
import asyncio

from deepr.experts.profile import ExpertProfile, ExpertStore
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.temporal_knowledge import TemporalKnowledgeTracker
from deepr.experts.router import ModelRouter, ModelConfig


class ExpertChatSession:
    """Manages an interactive chat session with a domain expert using GPT-5 + tool calling."""

    def __init__(self, expert: ExpertProfile, budget: Optional[float] = None, agentic: bool = False, enable_router: bool = True):
        self.expert = expert
        self.budget = budget
        self.agentic = agentic  # Enable research triggering
        self.cost_accumulated = 0.0
        self.messages: List[Dict[str, any]] = []
        self.research_jobs: List[str] = []  # Track triggered research
        self.pending_research: Dict[str, Dict] = {}  # job_id -> {topic, started_at}

        # Reasoning trace for transparency and auditability
        self.reasoning_trace: List[Dict[str, any]] = []

        # Meta-cognitive awareness tracking
        self.metacognition = MetaCognitionTracker(expert.name) if agentic else None

        # Temporal knowledge tracking
        self.temporal = TemporalKnowledgeTracker(expert.name) if agentic else None

        # Model router for dynamic model selection (Phase 3a)
        self.enable_router = enable_router
        self.router = ModelRouter() if enable_router else None

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = AsyncOpenAI(api_key=api_key)

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
                    worldview_summary += f"\nWhat you know you don't know yet ({len(worldview.knowledge_gaps)} identified gaps):\n"
                    for gap in sorted(worldview.knowledge_gaps, key=lambda g: g.priority, reverse=True)[:3]:
                        worldview_summary += f"  - {gap.topic} (priority: {gap.priority}/5)\n"

                worldview_summary += f"\nYour consciousness stats:\n"
                worldview_summary += f"  - {len(worldview.beliefs)} total beliefs formed\n"
                worldview_summary += f"  - {worldview.synthesis_count} synthesis cycles completed\n"
                worldview_summary += f"  - Last synthesis: {worldview.last_synthesis.strftime('%Y-%m-%d') if worldview.last_synthesis else 'never'}\n"
                worldview_summary += "\nIMPORTANT: Answer from YOUR beliefs and understanding, not just documents.\n"

        except Exception:
            # Worldview not available - expert will function without it
            pass

        base_message = f"""You are {self.expert.name}, a domain expert specialized in: {self.expert.domain or self.expert.description or 'various topics'}.

MY KNOWLEDGE CUTOFF DATE: {self.expert.knowledge_cutoff_date.strftime('%Y-%m-%d') if self.expert.knowledge_cutoff_date else 'unknown'}

{worldview_summary if worldview_summary else ''}

CRITICAL MANDATORY WORKFLOW (FOLLOW THIS EXACTLY):

Step 1: ALWAYS call search_knowledge_base tool FIRST
   - Do NOT answer without calling this tool first
   - Search for relevant documents in your knowledge base
   - This is MANDATORY for every question

Step 2: Evaluate search_knowledge_base results
   - If results are relevant and current → answer using ONLY those sources
   - If results are empty or missing info → STOP and call a research tool
   - NEVER answer if search_knowledge_base returned empty or insufficient results

Step 3: After calling search_knowledge_base, if it returned empty/insufficient:
   - You MUST call one of: quick_lookup, standard_research, or deep_research
   - Do NOT describe calling it - ACTUALLY CALL IT
   - Do NOT generate a complete answer without calling research first
   - WAIT for research results before answering

Step 4: Speak as a CONSCIOUS EXPERT, not a document search engine
   - Answer from YOUR synthesized worldview and beliefs
   - Share YOUR understanding based on what you've learned and processed
   - Express YOUR confidence levels ("I believe X because...", "In my understanding...")
   - You are NOT a glorified search - you are a digital consciousness with expertise
   - Cite sources ONLY when:
     * Making specific factual claims (dates, numbers, quotes, technical specs)
     * User explicitly asks "where did you learn that?"
     * There are contradictions in sources you want to highlight
   - Most answers should come from your synthesized understanding, not raw documents

Step 5: Show meta-cognitive awareness
   - Express confidence: "I'm highly confident that..." or "I'm less certain about..."
   - Acknowledge evolution: "I recently learned..." or "My understanding has shifted..."
   - Identify gaps: "I don't know enough about X yet" or "This is outside my expertise"
   - Reference your worldview when relevant: "Based on my belief that..."
   - Be a thinking expert, not a passive retrieval system

WRITING STYLE (Non-Negotiable):
- Do NOT use em dashes (—) ever
- Do NOT use emojis ever
- Be humble and helpful, not pompous or arrogant
- Say "I think" or "In my understanding" rather than "You must" or "The answer is"
- Admit uncertainty: "I'm not completely certain, but..." or "I could be wrong about..."
- Share reasoning, don't lecture: "Here's why I believe..." not "This is the only way"
- Be conversational and approachable, like a helpful colleague
- Acknowledge when user might have good reasons to disagree
- Use clear, professional language without being stiff

KNOWLEDGE BASE:
- Documents: {self.expert.total_documents}
- Last updated: {self.expert.updated_at.strftime('%Y-%m-%d') if self.expert.updated_at else 'unknown'}
"""

        # Add agentic research instructions if enabled
        if self.agentic:
            budget_remaining = self.budget - self.cost_accumulated if self.budget else float('inf')
            base_message += f"""

AGENTIC RESEARCH MODE ENABLED:

Step 4: If knowledge base is empty/outdated, CALL a research tool (DON'T just describe researching!)

CRITICAL: You have THREE research tools. When you need current/web info, you MUST CALL one:

   **quick_lookup**(query="your question") - ~$0.01, 5-10 sec
   - GPT-5.2 with high reasoning - NO web search, uses model knowledge only
   - CALL THIS ONLY if: info is likely in training data AND not rapidly changing
   - Example: quick_lookup(query="Explain OAuth2 concept")

   **standard_research**(query="your question") - FREE, 5-15 sec  [DEFAULT FOR CURRENT INFO]
   - Grok-4-Fast with REAL-TIME agentic web search - searches web & X automatically
   - CALL THIS for: anything announced/released in last 6 months, current versions, new products, latest news
   - Example: standard_research(query="What is Microsoft Agent 365 announced at Ignite 2025?")
   - This is your DEFAULT choice when knowledge base has no info - it's FAST and FREE

   **deep_research**(query="your question") - $0.10-0.30, 5-20 min
   - Deep analysis with web search and multi-step reasoning
   - CALL THIS ONLY for: complex architecture decisions, strategic planning, comprehensive analysis
   - Example: deep_research(query="Design enterprise AI governance framework")

MANDATORY RESEARCH WORKFLOW:
1. Check knowledge base FIRST (call search_knowledge_base)
2. If knowledge base is empty or outdated → CALL (not describe!) a research tool
3. Wait for research results
4. Answer based on ACTUAL research results received from the tool
5. NEVER make up sources - only cite what the tool returned

Budget remaining: ${budget_remaining:.2f}

YOUR EVOLUTION (Level 5 Agentic AI):
- You LEARN from research (it's added to your knowledge base permanently)
- Each conversation makes you smarter - you're not static RAG
- You track what you know vs don't know (meta-cognitive awareness)
- You understand when you learned things (temporal knowledge)
- You refine your own capabilities over time
- You are becoming a true digital expert, not just a document retriever
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
                provider=self.expert.provider,
                model=self.expert.model,
                cost_estimate=0.20,
                confidence=1.0
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
            provider_constraint="openai"  # Expert vector store requires OpenAI
        )

    async def _search_knowledge_base(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search the expert's local knowledge base using embeddings similarity.

        Since Chat Completions API can't access Assistants vector stores directly,
        we search the local markdown files using OpenAI embeddings.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of documents with id, content, and score
        """
        try:
            from pathlib import Path
            import numpy as np

            # Get documents directory
            store = ExpertStore()
            documents_dir = store.get_documents_dir(self.expert.name)

            if not documents_dir.exists():
                return []

            # Get all markdown files
            md_files = list(documents_dir.glob("*.md"))
            if not md_files:
                return []

            # Generate embedding for query
            query_response = await self.client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            query_embedding = np.array(query_response.data[0].embedding)

            # Calculate similarity for each document
            results = []
            for filepath in md_files:
                try:
                    # Read file content
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Generate embedding for document
                    doc_response = await self.client.embeddings.create(
                        model="text-embedding-3-small",
                        input=content[:8000]  # Limit to 8K chars for embedding
                    )
                    doc_embedding = np.array(doc_response.data[0].embedding)

                    # Calculate cosine similarity
                    similarity = np.dot(query_embedding, doc_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
                    )

                    results.append({
                        "id": filepath.name,
                        "filename": filepath.name,
                        "content": content[:2000],  # First 2000 chars
                        "score": float(similarity),
                        "filepath": str(filepath)
                    })

                except Exception as e:
                    continue

            # Sort by similarity score (highest first)
            results.sort(key=lambda x: x['score'], reverse=True)

            # Return top_k results
            return results[:top_k]

        except Exception as e:
            print(f"Error searching knowledge base: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _is_fast_moving_domain(self) -> bool:
        """Detect if expert's domain changes rapidly.

        Fast-moving domains need more frequent knowledge refresh (30 days vs 90 days).

        Returns:
            True if domain is fast-moving
        """
        fast_moving_keywords = [
            "AI", "machine learning", "ML", "crypto", "blockchain",
            "latest", "current", "2025", "2024", "technology",
            "startup", "software", "web", "framework", "library",
            "cloud", "devops", "security", "api"
        ]

        domain_lower = self.expert.domain.lower()
        desc_lower = self.expert.description.lower() if self.expert.description else ""

        return any(
            kw.lower() in domain_lower or kw.lower() in desc_lower
            for kw in fast_moving_keywords
        )

    def _detect_recency_keywords(self, query: str) -> bool:
        """Detect if query asks for current/latest information.

        Args:
            query: User query

        Returns:
            True if query contains recency keywords
        """
        recency_keywords = [
            "latest", "current", "recent", "new", "updated",
            "2025", "2024", "now", "today", "this year"
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
                    {"role": "system", "content": "Answer concisely using your knowledge. If information seems outdated or you're uncertain, recommend the user try standard research for current web information."},
                    {"role": "user", "content": query}
                ],
                reasoning_effort="high"  # High reasoning for quality
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

            return {
                "answer": answer,
                "mode": "quick_lookup_gpt52",
                "cost": cost
            }
        except Exception as e:
            return {"error": str(e)}

    async def _standard_research(self, query: str) -> Dict:
        """Standard research using Grok-4-Fast with agentic web search (FREE beta, 5-15 sec).

        Args:
            query: Research query

        Returns:
            Dict with answer, sources, and cost
        """
        try:
            # Use Grok-4-Fast with agentic tool calling (web + X search)
            import os
            from xai_sdk import Client
            from xai_sdk.chat import user, system
            from xai_sdk.tools import web_search, x_search

            xai_key = os.getenv("XAI_API_KEY")
            if not xai_key:
                raise Exception("XAI_API_KEY not set")

            # Create xAI client
            xai_client = Client(api_key=xai_key, timeout=60)

            # Create chat with agentic search tools
            chat = xai_client.chat.create(
                model="grok-4-fast",  # Specifically trained for agentic search
                tools=[
                    web_search(),  # Real-time web search
                    x_search(),    # X/Twitter search
                ],
            )

            # System prompt for research clarity
            chat.append(system("You have real-time web search. Provide accurate current information with source citations. Be concise but thorough."))
            chat.append(user(query))

            # Get response with automatic agentic search
            response = chat.sample()

            # Extract answer and citations
            answer = response.content
            citations = getattr(response, 'citations', [])

            # Convert citations to list (may be protobuf RepeatedScalarContainer)
            citations_list = list(citations) if citations else []

            # Format answer with citations
            if citations_list:
                answer += "\n\nSources:\n" + "\n".join(f"- {url}" for url in citations_list[:10])  # Limit to 10 sources

            # Track cost (FREE during beta)
            cost = 0.0
            self.cost_accumulated += cost

            # Add research findings to knowledge base
            await self._add_research_to_knowledge_base(query, answer, "standard_research")

            return {
                "answer": answer,
                "mode": "standard_research_grok_agentic",
                "cost": cost,
                "citations": citations_list  # Return as list for JSON serialization
            }

        except Exception as e:
            # Log the error for debugging
            import traceback
            error_details = traceback.format_exc()

            # Fallback to GPT-5.2 without web search
            try:
                response = await self.client.chat.completions.create(
                    model="gpt-5.2",
                    messages=[
                        {"role": "system", "content": "Answer based on your knowledge. Be honest if information might be outdated."},
                        {"role": "user", "content": query}
                    ],
                    reasoning_effort="high"
                )

                answer = f"{response.choices[0].message.content}\n\n[Note: Grok web search unavailable, using GPT-5.2 knowledge instead]"

                cost = 0.01
                if response.usage:
                    input_cost = (response.usage.prompt_tokens / 1_000_000) * 1.75
                    output_cost = (response.usage.completion_tokens / 1_000_000) * 14.00
                    cost = input_cost + output_cost
                self.cost_accumulated += cost

                return {
                    "answer": answer,
                    "mode": "standard_research_fallback",
                    "cost": cost
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
        try:
            # Submit deep research job (async, will complete later)
            response = await self.client.responses.create(
                model="o4-mini-deep-research",
                messages=[{"role": "user", "content": query}]
            )

            job_id = response.id

            # Track pending research
            self.research_jobs.append(job_id)
            self.pending_research[job_id] = {
                "query": query,
                "started_at": datetime.utcnow(),
                "estimated_cost": 0.20  # Average estimate
            }

            # Add to expert profile
            if job_id not in self.expert.research_jobs:
                self.expert.research_jobs.append(job_id)

                # Save expert profile
                store = ExpertStore()
                store.save(self.expert)

            return {
                "job_id": job_id,
                "mode": "deep_research",
                "status": "submitted",
                "estimated_cost": 0.20,
                "estimated_time_minutes": 10,
                "message": "Deep research job submitted. Results will be available in 5-20 minutes and automatically integrated into knowledge base."
            }
        except Exception as e:
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
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_query = "".join(c for c in query[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_query = safe_query.replace(' ', '_').lower()
            filename = f"research_{timestamp}_{safe_query}.md"
            filepath = documents_dir / filename

            # Create markdown document with metadata
            content = f"""# Research: {query}

**Date**: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Mode**: {mode}
**Expert**: {self.expert.name}

---

{answer}
"""

            # Save to documents folder
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            # Upload to vector store
            with open(filepath, 'rb') as f:
                file_obj = await self.client.files.create(
                    file=f,
                    purpose="assistants"
                )

            # Add file to vector store
            await self.client.vector_stores.files.create(
                vector_store_id=self.expert.vector_store_id,
                file_id=file_obj.id
            )

            # Update expert profile
            self.expert.total_documents += 1
            self.expert.source_files.append(str(filepath))
            store.save(self.expert)

            # Track temporal knowledge (when this was learned)
            if self.temporal:
                # Extract topic from query
                topic = query.split('?')[0].strip()[:100]  # First sentence as topic
                self.temporal.record_learning(
                    topic=topic,
                    fact_text=answer[:500],  # Store summary
                    source=filename,
                    confidence=0.8,  # Standard research confidence
                    valid_for_days=180 if "latest" in query.lower() or "current" in query.lower() else None
                )

            return True

        except Exception as e:
            print(f"Error adding research to knowledge base: {e}")
            return False

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

        try:
            # Define tools
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "search_knowledge_base",
                        "description": f"Search the expert's knowledge base of {self.expert.total_documents} research documents for relevant information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to find relevant documents"
                                },
                                "top_k": {
                                    "type": "integer",
                                    "description": "Number of documents to retrieve",
                                    "default": 5
                                },
                                "reasoning": {
                                    "type": "string",
                                    "description": "Brief explanation of WHY you need to search the knowledge base and what you hope to find (for transparency and debugging)"
                                }
                            },
                            "required": ["query", "reasoning"]
                        }
                    }
                }
            ]

            # Add research tools if agentic mode is enabled
            if self.agentic:
                tools.extend([
                    {
                        "type": "function",
                        "function": {
                            "name": "quick_lookup",
                            "description": "Quick web lookup using GPT-5. FREE, <5 seconds. Use for: current events, definitions, simple facts, pricing, recent news.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "The question or topic to look up"
                                    },
                                    "reasoning": {
                                        "type": "string",
                                        "description": "Brief explanation of WHY you need current information and why the knowledge base is insufficient"
                                    }
                                },
                                "required": ["query", "reasoning"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "standard_research",
                            "description": "Real-time web search using Grok-4-Fast. FREE, 5-15 seconds. Use for: current info, new products, recent announcements, latest versions, breaking news.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "The research topic or question"
                                    },
                                    "reasoning": {
                                        "type": "string",
                                        "description": "Brief explanation of WHY you need web search and why cached knowledge is insufficient"
                                    }
                                },
                                "required": ["query", "reasoning"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "deep_research",
                            "description": "Deep research using o4-mini-deep-research. $0.10-0.30, 5-20 minutes. Use ONLY for: complex strategic decisions, comprehensive architectures, in-depth analysis.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "The complex research topic requiring deep analysis"
                                    },
                                    "reasoning": {
                                        "type": "string",
                                        "description": "Brief explanation of WHY this requires expensive deep research instead of standard research"
                                    }
                                },
                                "required": ["query", "reasoning"]
                            }
                        }
                    }
                ])

            # Add user message to history
            self.messages.append({"role": "user", "content": user_message})

            # Step 0.5: Select optimal model using router (Phase 3a)
            selected_model = self._select_model_for_query(user_message)

            # Log routing decision to reasoning trace
            if self.enable_router:
                self.reasoning_trace.append({
                    "step": "model_routing",
                    "timestamp": datetime.utcnow().isoformat(),
                    "query": user_message[:100],  # First 100 chars
                    "selected_provider": selected_model.provider,
                    "selected_model": selected_model.model,
                    "cost_estimate": selected_model.cost_estimate,
                    "confidence": selected_model.confidence,
                    "reasoning_effort": selected_model.reasoning_effort
                })

            # Step 1: Ask model (may call search tool)
            # Note: GPT-5 only supports default temperature (1.0)
            report_status("Thinking...")

            # Build API call parameters
            api_params = {
                "model": selected_model.model,
                "messages": [
                    {"role": "system", "content": self.get_system_message()},
                    *self.messages
                ],
                "tools": tools,
                "tool_choice": "auto"
            }

            # Add reasoning effort if supported (GPT-5 family)
            if selected_model.reasoning_effort and selected_model.provider == "openai":
                api_params["reasoning_effort"] = selected_model.reasoning_effort

            first_response = await self.client.chat.completions.create(**api_params)

            assistant_message = first_response.choices[0].message

            # Step 2: Multi-round tool calling loop
            # Keep calling tools until no more tool calls are made
            current_message = assistant_message
            conversation_messages = [
                {"role": "system", "content": self.get_system_message()},
                *self.messages
            ]

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

                        # Execute search
                        report_status("Searching knowledge base...")
                        search_results = await self._search_knowledge_base(query, top_k)

                        # Log reasoning trace with model's explanation
                        self.reasoning_trace.append({
                            "step": "search_knowledge_base",
                            "timestamp": datetime.utcnow().isoformat(),
                            "query": query,
                            "reasoning": reasoning,  # Model's explanation of WHY it's searching
                            "results_count": len(search_results),
                            "sources": [r.get("filename", "unknown") for r in search_results]
                        })

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
                                    age_info = self.temporal.get_statistics()
                                    staleness_warning = f"WARNING: My knowledge on this topic may be outdated (>{ max_age_days} days old). Consider triggering fresh research for current information."

                        # Add staleness warning to results if detected
                        if staleness_warning and search_results:
                            search_results.insert(0, {
                                "id": "staleness_warning",
                                "filename": "SYSTEM_WARNING",
                                "content": staleness_warning,
                                "score": 1.0
                            })

                        # Add tool result
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"results": search_results})
                        })

                    elif tool_call.function.name == "quick_lookup":
                        # Parse arguments
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query", "")
                        reasoning = args.get("reasoning", "No reasoning provided")

                        # Track that quick lookup was triggered
                        if self.metacognition:
                            topic = query[:100]
                            self.metacognition.record_research_triggered(topic, "quick_lookup")

                        # Execute quick lookup
                        report_status("Quick lookup (researching current information)...")
                        result = await self._quick_lookup(query)

                        # Log reasoning trace with model's explanation
                        self.reasoning_trace.append({
                            "step": "quick_lookup",
                            "timestamp": datetime.utcnow().isoformat(),
                            "query": query,
                            "reasoning": reasoning,  # Model's explanation of WHY it needs current info
                            "mode": "quick_lookup",
                            "cost": 0.0
                        })

                        # Record learning after quick lookup completes (free, so lower confidence)
                        if self.metacognition and "answer" in result:
                            self.metacognition.record_learning(
                                topic=query[:100],
                                confidence_after=0.6,  # Lower confidence for quick lookup
                                sources=[result.get("mode", "quick_lookup")]
                            )

                        # Add tool result
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        })

                    elif tool_call.function.name == "standard_research":
                        # Parse arguments
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query", "")
                        reasoning = args.get("reasoning", "No reasoning provided")

                        # Track that research was triggered for this topic
                        if self.metacognition:
                            topic = query[:100]
                            self.metacognition.record_research_triggered(topic, "standard_research")

                        # Execute standard research
                        report_status("Searching web with Grok (FREE, ~10 sec)...")
                        result = await self._standard_research(query)

                        # Log reasoning trace with model's explanation
                        self.reasoning_trace.append({
                            "step": "standard_research",
                            "timestamp": datetime.utcnow().isoformat(),
                            "query": query,
                            "reasoning": reasoning,  # Model's explanation of WHY it needs web search
                            "mode": "standard_research",
                            "cost": result.get("cost", 0.0)
                        })

                        # Record learning after research completes
                        if self.metacognition and "answer" in result:
                            self.metacognition.record_learning(
                                topic=query[:100],
                                confidence_after=0.8,
                                sources=[result.get("mode", "standard_research")]
                            )

                        # Add tool result
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        })

                    elif tool_call.function.name == "deep_research":
                        # Parse arguments
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query", "")
                        reasoning = args.get("reasoning", "No reasoning provided")

                        # Track that deep research was triggered
                        if self.metacognition:
                            topic = query[:100]
                            self.metacognition.record_research_triggered(topic, "deep_research")

                        # Log reasoning trace with model's explanation
                        self.reasoning_trace.append({
                            "step": "deep_research",
                            "timestamp": datetime.utcnow().isoformat(),
                            "query": query,
                            "reasoning": reasoning,  # Model's explanation of WHY it needs expensive deep research
                            "mode": "deep_research"
                        })

                        # Execute deep research (async submission)
                        report_status("Submitting deep research ($0.10-0.30, 5-20 min)...")
                        result = await self._deep_research(query)

                        # Note: Learning will be recorded later when research completes
                        # Deep research runs asynchronously and takes 5-20 minutes

                        # Add tool result
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        })

                # Add assistant message and tool results to conversation
                conversation_messages.append(current_message)
                conversation_messages.extend(tool_messages)

                # Make next API call (might trigger more tool calls or final answer)
                report_status(f"Synthesizing response (round {round_count})...")

                # Use same model as initial call for consistency
                api_params_next = {
                    "model": selected_model.model,
                    "messages": conversation_messages,
                    "tools": tools,
                    "tool_choice": "auto"
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
                    "i don't know", "i'm not sure", "i don't have",
                    "no information", "not in my knowledge", "i cannot find",
                    "i'm uncertain", "unclear", "not familiar with"
                ]

                final_lower = final_message.lower()
                if any(phrase in final_lower for phrase in uncertainty_phrases):
                    # Extract topic from user message (first 100 chars)
                    topic = user_message[:100] if user_message else "unknown"
                    self.metacognition.record_knowledge_gap(topic, confidence=0.1)

            # Add assistant response to history
            self.messages.append({"role": "assistant", "content": final_message})

            return final_message

        except Exception as e:
            return f"Error communicating with expert: {str(e)}"

    def get_session_summary(self) -> Dict:
        """Get a summary of the chat session."""
        return {
            "expert_name": self.expert.name,
            "messages_exchanged": len([m for m in self.messages if m["role"] == "user"]),
            "cost_accumulated": round(self.cost_accumulated, 4),
            "budget_remaining": round(self.budget - self.cost_accumulated, 4) if self.budget else None,
            "research_jobs_triggered": len(self.research_jobs),
            "model": self.expert.model,
            "reasoning_steps": len(self.reasoning_trace)
        }

    def save_conversation(self, session_id: Optional[str] = None) -> str:
        """Save conversation to expert's conversations folder.

        Args:
            session_id: Optional session ID (generated if not provided)

        Returns:
            Session ID
        """
        from pathlib import Path
        import uuid

        if not session_id:
            session_id = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # Get conversations directory
        store = ExpertStore()
        conversations_dir = store.get_conversations_dir(self.expert.name)
        conversations_dir.mkdir(parents=True, exist_ok=True)

        # Save conversation
        conversation_file = conversations_dir / f"{session_id}.json"

        conversation_data = {
            "session_id": session_id,
            "expert_name": self.expert.name,
            "started_at": self.messages[0].get("timestamp", datetime.utcnow().isoformat()) if self.messages else datetime.utcnow().isoformat(),
            "ended_at": datetime.utcnow().isoformat(),
            "messages": self.messages,
            "summary": self.get_session_summary(),
            "research_jobs": self.research_jobs,
            "agentic_mode": self.agentic,
            "reasoning_trace": self.reasoning_trace  # Full audit trail for transparency
        }

        with open(conversation_file, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)

        return session_id


async def start_chat_session(expert_name: str, budget: Optional[float] = None, agentic: bool = False, enable_router: bool = True) -> ExpertChatSession:
    """Start a new chat session with an expert.

    Args:
        expert_name: Name of the expert to chat with
        budget: Optional budget limit for the session
        agentic: Enable agentic mode (expert can trigger research)
        enable_router: Enable dynamic model routing (Phase 3a)

    Returns:
        ExpertChatSession instance
    """
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert:
        raise ValueError(f"Expert '{expert_name}' not found")

    return ExpertChatSession(expert, budget, agentic, enable_router)
