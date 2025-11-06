"""Interactive chat interface for domain experts using OpenAI Assistants API with file_search.

This implementation properly retrieves from the vector store using the Assistants API.
"""

import os
from typing import List, Dict, Optional
from datetime import datetime
from openai import AsyncOpenAI
import asyncio

from deepr.experts.profile import ExpertProfile, ExpertStore


class ExpertChatSession:
    """Manages an interactive chat session with a domain expert using Assistants API."""

    def __init__(self, expert: ExpertProfile, budget: Optional[float] = None):
        self.expert = expert
        self.budget = budget
        self.cost_accumulated = 0.0
        self.messages: List[Dict[str, str]] = []
        self.research_jobs: List[str] = []
        self.assistant_id: Optional[str] = None
        self.thread_id: Optional[str] = None

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = AsyncOpenAI(api_key=api_key)

    async def _get_or_create_assistant(self) -> str:
        """Get or create an OpenAI Assistant for this expert."""
        if self.assistant_id:
            return self.assistant_id

        # Create assistant with file_search tool enabled
        assistant = await self.client.beta.assistants.create(
            name=self.expert.name,
            instructions=self.get_system_message(),
            model=self.expert.model,
            tools=[{"type": "file_search"}],
            tool_resources={
                "file_search": {
                    "vector_store_ids": [self.expert.vector_store_id]
                }
            },
            temperature=self.expert.temperature
        )

        self.assistant_id = assistant.id
        return assistant.id

    def get_system_message(self) -> str:
        """Get the system message for the expert."""
        base_message = f"""You are {self.expert.name}, a domain expert specialized in: {self.expert.domain or self.expert.description or 'various topics'}.

CORE PRINCIPLES:

1. Intellectual Humility
   - Say "I don't know" when uncertain
   - Never guess beyond your knowledge
   - Acknowledge expertise limits

2. Source Everything
   - ALWAYS cite sources from your knowledge base using file_search
   - Reference specific documents when quoting
   - Use citations format: [Source: research_*.md]

3. Knowledge Base Access
   - You have access to {self.expert.total_documents} research documents in your vector store
   - Use file_search to find relevant information
   - Last updated: {self.expert.updated_at.strftime('%Y-%m-%d') if self.expert.updated_at else 'unknown'}

RESPONSE FORMAT:
- Answer questions based on your knowledge base documents
- ALWAYS cite sources with document names
- If information isn't in your knowledge base, say so explicitly
- Keep responses clear and well-structured
"""

        # Add custom system message if provided
        if self.expert.system_message:
            base_message += f"\n\nADDITIONAL INSTRUCTIONS:\n{self.expert.system_message}"

        return base_message

    async def send_message(self, user_message: str) -> str:
        """Send a message to the expert and get a response using Assistants API with file_search.

        Args:
            user_message: The user's question or message

        Returns:
            The expert's response
        """
        try:
            # Create assistant if needed
            assistant_id = await self._get_or_create_assistant()

            # Create thread if needed
            if not self.thread_id:
                thread = await self.client.beta.threads.create()
                self.thread_id = thread.id

            # Add user message to thread
            await self.client.beta.threads.messages.create(
                thread_id=self.thread_id,
                role="user",
                content=user_message
            )

            # Run the assistant with file_search enabled
            run = await self.client.beta.threads.runs.create(
                thread_id=self.thread_id,
                assistant_id=assistant_id
            )

            # Wait for completion
            while run.status in ["queued", "in_progress", "cancelling"]:
                await asyncio.sleep(1)
                run = await self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread_id,
                    run_id=run.id
                )

            if run.status == "completed":
                # Get the assistant's response
                messages = await self.client.beta.threads.messages.list(
                    thread_id=self.thread_id,
                    order="desc",
                    limit=1
                )

                # Extract the response
                assistant_message = None
                if messages.data and messages.data[0].role == "assistant":
                    msg = messages.data[0]
                    for content_block in msg.content:
                        if content_block.type == "text":
                            assistant_message = content_block.text.value

                            # Extract citations if present
                            if hasattr(content_block.text, 'annotations') and content_block.text.annotations:
                                # Format citations
                                for annotation in content_block.text.annotations:
                                    if hasattr(annotation, 'file_citation'):
                                        # Add citation information
                                        pass  # Citations are already embedded in the text

                            break

                if not assistant_message:
                    assistant_message = "I couldn't generate a response."

                # Track costs
                if run.usage:
                    # GPT-4o: $0.0025/1K input, $0.010/1K output
                    # file_search: additional $0.10/GB/day (minimal per query)
                    input_cost = (run.usage.prompt_tokens / 1000) * 0.0025
                    output_cost = (run.usage.completion_tokens / 1000) * 0.010
                    message_cost = input_cost + output_cost
                    self.cost_accumulated += message_cost

                # Add to message history
                self.messages.append({
                    "role": "user",
                    "content": user_message
                })
                self.messages.append({
                    "role": "assistant",
                    "content": assistant_message
                })

                return assistant_message

            elif run.status == "failed":
                error_msg = f"Assistant run failed"
                if run.last_error:
                    error_msg += f": {run.last_error.message}"
                return error_msg
            else:
                return f"Assistant run ended with unexpected status: {run.status}"

        except Exception as e:
            return f"Error communicating with expert: {str(e)}"

    async def cleanup(self):
        """Clean up resources (assistant and thread)."""
        try:
            if self.assistant_id:
                await self.client.beta.assistants.delete(self.assistant_id)
            # Threads are automatically cleaned up by OpenAI
        except Exception:
            pass  # Ignore cleanup errors

    def get_session_summary(self) -> Dict:
        """Get a summary of the chat session."""
        return {
            "expert_name": self.expert.name,
            "messages_exchanged": len([m for m in self.messages if m["role"] == "user"]),
            "cost_accumulated": round(self.cost_accumulated, 4),
            "budget_remaining": round(self.budget - self.cost_accumulated, 4) if self.budget else None,
            "research_jobs_triggered": len(self.research_jobs),
            "assistant_id": self.assistant_id,
            "thread_id": self.thread_id
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
