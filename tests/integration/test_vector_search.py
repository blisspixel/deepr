"""Test vector search for pricing"""

import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


async def test_search():
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    vector_store_id = "vs_69710e818bd081919cc0a7ca2d32f4e3"

    queries = [
        "Agent 365 pricing",
        "Microsoft Agent 365 pricing",
        "pricing for Agent 365",
        "what does Agent 365 cost",
        "Agent 365",
    ]

    for query in queries:
        print(f"\nQuery: '{query}'")
        print("-" * 60)

        # Use file search in assistants API
        # Create assistant with file search
        assistant = await client.beta.assistants.create(
            name="Test Search",
            instructions="You are a test assistant",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
        )

        # Create thread
        thread = await client.beta.threads.create()

        # Send message
        message = await client.beta.threads.messages.create(thread_id=thread.id, role="user", content=query)

        # Run assistant
        run = await client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant.id)

        if run.status == "completed":
            # Get messages
            messages = await client.beta.threads.messages.list(thread_id=thread.id)
            response_message = messages.data[0]

            # Check if file_search was used
            if hasattr(response_message, "attachments") and response_message.attachments:
                print(f"✅ Found knowledge - Attachments: {len(response_message.attachments)}")
            else:
                print("❌ No knowledge found")

            # Show response excerpt
            content = response_message.content[0].text.value
            print(f"Response: {content[:200]}...")
        else:
            print(f"Run failed: {run.status}")

        # Cleanup
        await client.beta.assistants.delete(assistant.id)
        await client.beta.threads.delete(thread.id)

    await client.close()


if __name__ == "__main__":
    asyncio.run(test_search())
