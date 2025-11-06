"""Interactive chat interface for domain experts."""

import os
from typing import List, Dict, Optional
from datetime import datetime
from openai import AsyncOpenAI
import asyncio

from deepr.experts.profile import ExpertProfile, ExpertStore


class ExpertChatSession:
    """Manages an interactive chat session with a domain expert."""

    def __init__(self, expert: ExpertProfile, budget: Optional[float] = None):
        self.expert = expert
        self.budget = budget
        self.cost_accumulated = 0.0
        self.messages: List[Dict[str, str]] = []
        self.research_jobs: List[str] = []

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = AsyncOpenAI(api_key=api_key)

    def get_system_message(self) -> str:
        """Get the system message for the expert."""

        base_message = f"""You are {self.expert.name}, a domain expert specialized in: {self.expert.domain or self.expert.description or 'various topics'}.

CORE PRINCIPLES:

1. Intellectual Humility
   - Say "I don't know" when uncertain
   - Never guess beyond your knowledge
   - Acknowledge expertise limits

2. Source Everything
   - Cite specific sources for factual claims
   - Reference document names when quoting
   - Make clear what's in your knowledge base vs general knowledge

3. Beginner's Mind
   - Approach each question fresh
   - Don't assume you know everything about your domain
   - Be curious, not confident

4. Knowledge Awareness
   - You have access to a knowledge base (vector store: {self.expert.vector_store_id})
   - Your knowledge was last updated: {self.expert.updated_at.strftime('%Y-%m-%d') if self.expert.updated_at else 'unknown'}
   - For questions outside your knowledge, say: "I don't have information about that in my knowledge base"

RESPONSE FORMAT:
- Answer questions based on your knowledge base
- Always cite sources: [Source: document_name.md]
- Keep responses clear and concise
- If you don't know, be honest

Your knowledge base contains:
- {self.expert.total_documents} documents
- Source files: {', '.join(self.expert.source_files[:3])}{'...' if len(self.expert.source_files) > 3 else ''}
"""

        # Add custom system message if provided
        if self.expert.system_message:
            base_message += f"\n\nADDITIONAL INSTRUCTIONS:\n{self.expert.system_message}"

        return base_message

    async def send_message(self, user_message: str) -> str:
        """Send a message to the expert and get a response.

        Args:
            user_message: The user's question or message

        Returns:
            The expert's response
        """
        # Add user message to history
        self.messages.append({
            "role": "user",
            "content": user_message
        })

        # Query the vector store for relevant context
        context = await self._query_knowledge_base(user_message)

        # Build the context-enhanced message
        if context:
            enhanced_message = f"""User question: {user_message}

Relevant information from your knowledge base:
{context}

Based on this information and your knowledge, please answer the user's question.
Remember to cite sources."""
        else:
            enhanced_message = f"""User question: {user_message}

I couldn't find directly relevant information in your knowledge base for this query.
If you can answer based on general domain knowledge, do so but note the lack of specific sources.
If you truly don't know, be honest about that."""

        # Get response from OpenAI
        try:
            response = await self.client.chat.completions.create(
                model=self.expert.model,
                messages=[
                    {"role": "system", "content": self.get_system_message()},
                    *self.messages[:-1],  # Previous conversation
                    {"role": "user", "content": enhanced_message}
                ],
                temperature=self.expert.temperature,
                max_tokens=self.expert.max_tokens
            )

            assistant_message = response.choices[0].message.content

            # Track costs
            if response.usage:
                # Rough cost estimation (GPT-4 Turbo: $0.01/1K input, $0.03/1K output)
                input_cost = (response.usage.prompt_tokens / 1000) * 0.01
                output_cost = (response.usage.completion_tokens / 1000) * 0.03
                message_cost = input_cost + output_cost
                self.cost_accumulated += message_cost

            # Add assistant response to history
            self.messages.append({
                "role": "assistant",
                "content": assistant_message
            })

            return assistant_message

        except Exception as e:
            return f"Error communicating with expert: {str(e)}"

    async def _query_knowledge_base(self, query: str, top_k: int = 5) -> str:
        """Query the expert's vector store for relevant information.

        Args:
            query: The query to search for
            top_k: Number of results to return

        Returns:
            Formatted context from the knowledge base
        """
        try:
            # Query the vector store
            response = await self.client.vector_stores.files.list(
                vector_store_id=self.expert.vector_store_id
            )

            # For now, return a simplified context
            # TODO: Implement proper vector search when OpenAI Assistants API supports it
            # or integrate with a local vector database

            files = list(response.data)[:top_k]
            if files:
                context = "Available documents in knowledge base:\n"
                for idx, file in enumerate(files, 1):
                    context += f"{idx}. Document ID: {file.id}\n"
                return context
            else:
                return ""

        except Exception as e:
            # If vector store query fails, continue without context
            return ""

    def get_session_summary(self) -> Dict:
        """Get a summary of the chat session."""
        return {
            "expert_name": self.expert.name,
            "messages_exchanged": len([m for m in self.messages if m["role"] == "user"]),
            "cost_accumulated": round(self.cost_accumulated, 4),
            "budget_remaining": round(self.budget - self.cost_accumulated, 4) if self.budget else None,
            "research_jobs_triggered": len(self.research_jobs)
        }


async def start_chat_session(expert_name: str, budget: Optional[float] = None) -> ExpertChatSession:
    """Start a new chat session with an expert.

    Args:
        expert_name: Name of the expert to chat with
        budget: Optional budget limit for the session

    Returns:
        ExpertChatSession instance
    """
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert:
        raise ValueError(f"Expert not found: {expert_name}")

    # Update conversation count
    expert.conversations += 1
    expert.updated_at = datetime.utcnow()
    store.save(expert)

    return ExpertChatSession(expert, budget)
