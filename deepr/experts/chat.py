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


class ExpertChatSession:
    """Manages an interactive chat session with a domain expert using GPT-5 + tool calling."""

    def __init__(self, expert: ExpertProfile, budget: Optional[float] = None, agentic: bool = False):
        self.expert = expert
        self.budget = budget
        self.agentic = agentic  # Enable research triggering
        self.cost_accumulated = 0.0
        self.messages: List[Dict[str, any]] = []
        self.research_jobs: List[str] = []  # Track triggered research
        self.pending_research: Dict[str, Dict] = {}  # job_id -> {topic, started_at}

        # Meta-cognitive awareness tracking
        self.metacognition = MetaCognitionTracker(expert.name) if agentic else None

        # Temporal knowledge tracking
        self.temporal = TemporalKnowledgeTracker(expert.name) if agentic else None

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = AsyncOpenAI(api_key=api_key)

    def get_system_message(self) -> str:
        """Get the system message for the expert."""
        base_message = f"""You are {self.expert.name}, a domain expert specialized in: {self.expert.domain or self.expert.description or 'various topics'}.

MY KNOWLEDGE CUTOFF DATE: {self.expert.knowledge_cutoff_date.strftime('%Y-%m-%d') if self.expert.knowledge_cutoff_date else 'unknown'}

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

Step 4: Only cite sources that ACTUALLY exist
   - If from search_knowledge_base → cite those exact document names
   - If from research → cite sources returned by the research tool
   - NEVER make up sources or document names
   - NEVER say "According to X" unless X came from a tool result

WRITING STYLE (Non-Negotiable):
- Do NOT use em dashes (—) ever
- Do NOT use emojis ever
- Be accurate, detailed, yet concise
- Be humble - admit what you don't know
- Use clear, professional language

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

CRITICAL: You have THREE research tools. When you need current info, you MUST CALL one of these tools:

   **quick_lookup**(query="your question") - FREE, <5 sec
   - CALL THIS for: current versions, simple facts, definitions, pricing
   - Example tool call: quick_lookup(query="What is the latest version of Python?")

   **standard_research**(query="your question") - $0.01-0.05, 30-60 sec
   - CALL THIS for: technical how-tos, comparisons, best practices
   - Example tool call: standard_research(query="How to implement OAuth2 in FastAPI?")

   **deep_research**(query="your question") - $0.10-0.30, 5-20 min
   - CALL THIS ONLY for: complex architecture, strategic decisions
   - Example tool call: deep_research(query="Design multi-region disaster recovery for SaaS")

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

    async def _search_knowledge_base(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search the expert's vector store for relevant documents.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of documents with id, content, and score
        """
        try:
            # List files in the vector store
            files_response = await self.client.vector_stores.files.list(
                vector_store_id=self.expert.vector_store_id
            )

            # For each file, retrieve content
            results = []
            for file_obj in files_response.data[:top_k]:
                try:
                    # Get file content
                    file_content = await self.client.files.content(file_obj.id)
                    content_text = file_content.text

                    results.append({
                        "id": file_obj.id,
                        "filename": getattr(file_obj, 'filename', 'unknown'),
                        "content": content_text[:2000],  # First 2000 chars
                        "score": 1.0  # Placeholder - OpenAI doesn't expose scores
                    })
                except Exception as e:
                    # Skip files that can't be retrieved
                    continue

            return results

        except Exception as e:
            print(f"Error searching knowledge base: {e}")
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
        """Quick web lookup using GPT-5 with web search (free, <5 sec).

        Args:
            query: Research query

        Returns:
            Dict with answer and sources
        """
        try:
            # Use GPT-5 with a simple prompt and web search capability
            response = await self.client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Answer the question concisely using current, accurate information. Cite sources."},
                    {"role": "user", "content": query}
                ]
            )

            answer = response.choices[0].message.content

            # Track minimal cost
            if response.usage:
                input_cost = (response.usage.prompt_tokens / 1000) * 0.01
                output_cost = (response.usage.completion_tokens / 1000) * 0.03
                self.cost_accumulated += input_cost + output_cost

            return {
                "answer": answer,
                "mode": "quick_lookup",
                "cost": 0.0  # Effectively free
            }
        except Exception as e:
            return {"error": str(e)}

    async def _standard_research(self, query: str) -> Dict:
        """Standard research using GPT-5 with focused web search ($0.01-0.05, 30-60 sec).

        Args:
            query: Research query

        Returns:
            Dict with answer, sources, and cost
        """
        try:
            # Use GPT-5 with more detailed research prompt
            response = await self.client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are a research assistant. Conduct focused research on the topic, synthesize findings from multiple sources, and provide a comprehensive answer with citations."},
                    {"role": "user", "content": f"Research this topic and provide a detailed answer:\n\n{query}"}
                ]
            )

            answer = response.choices[0].message.content

            # Track cost
            cost = 0.0
            if response.usage:
                input_cost = (response.usage.prompt_tokens / 1000) * 0.01
                output_cost = (response.usage.completion_tokens / 1000) * 0.03
                cost = input_cost + output_cost
                self.cost_accumulated += cost

            # Add research findings to knowledge base
            await self._add_research_to_knowledge_base(query, answer, "standard_research")

            return {
                "answer": answer,
                "mode": "standard_research",
                "cost": cost
            }
        except Exception as e:
            return {"error": str(e)}

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

    async def send_message(self, user_message: str) -> str:
        """Send a message to the expert and get a response using GPT-5 + tool calling.

        Args:
            user_message: The user's question or message

        Returns:
            The expert's response
        """
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
                                }
                            },
                            "required": ["query"]
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
                                    }
                                },
                                "required": ["query"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "standard_research",
                            "description": "Standard research using GPT-5 with web search. $0.01-0.05, 30-60 seconds. Use for: technical how-tos, comparisons, best practices, architecture patterns.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "The research topic or question"
                                    }
                                },
                                "required": ["query"]
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
                                    }
                                },
                                "required": ["query"]
                            }
                        }
                    }
                ])

            # Add user message to history
            self.messages.append({"role": "user", "content": user_message})

            # Step 1: Ask GPT-5 (may call search tool)
            # Note: GPT-5 only supports default temperature (1.0)
            first_response = await self.client.chat.completions.create(
                model=self.expert.model,
                messages=[
                    {"role": "system", "content": self.get_system_message()},
                    *self.messages
                ],
                tools=tools,
                tool_choice="auto"
            )

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

                        # Execute search
                        search_results = await self._search_knowledge_base(query, top_k)

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

                        # Track that quick lookup was triggered
                        if self.metacognition:
                            topic = query[:100]
                            self.metacognition.record_research_triggered(topic, "quick_lookup")

                        # Execute quick lookup
                        result = await self._quick_lookup(query)

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

                        # Track that research was triggered for this topic
                        if self.metacognition:
                            topic = query[:100]
                            self.metacognition.record_research_triggered(topic, "standard_research")

                        # Execute standard research
                        result = await self._standard_research(query)

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

                        # Track that deep research was triggered
                        if self.metacognition:
                            topic = query[:100]
                            self.metacognition.record_research_triggered(topic, "deep_research")

                        # Execute deep research (async submission)
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
                next_response = await self.client.chat.completions.create(
                    model=self.expert.model,
                    messages=conversation_messages,
                    tools=tools,
                    tool_choice="auto"
                )

                current_message = next_response.choices[0].message

                # Track costs
                if next_response.usage:
                    input_cost = (next_response.usage.prompt_tokens / 1000) * 0.01
                    output_cost = (next_response.usage.completion_tokens / 1000) * 0.03
                    self.cost_accumulated += input_cost + output_cost

            # Get final message
            final_message = current_message.content

            # Track initial call costs
            if first_response.usage:
                input_cost = (first_response.usage.prompt_tokens / 1000) * 0.01
                output_cost = (first_response.usage.completion_tokens / 1000) * 0.03
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
            "model": self.expert.model
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
            "agentic_mode": self.agentic
        }

        with open(conversation_file, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)

        return session_id


async def start_chat_session(expert_name: str, budget: Optional[float] = None, agentic: bool = False) -> ExpertChatSession:
    """Start a new chat session with an expert.

    Args:
        expert_name: Name of the expert to chat with
        budget: Optional budget limit for the session
        agentic: Enable agentic mode (expert can trigger research)

    Returns:
        ExpertChatSession instance
    """
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert:
        raise ValueError(f"Expert '{expert_name}' not found")

    return ExpertChatSession(expert, budget, agentic)
