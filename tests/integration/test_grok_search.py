"""Test Grok agentic web search directly"""
import os
import asyncio
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import user, system
from xai_sdk.tools import web_search, x_search

# Load .env file
load_dotenv()

async def test_grok():
    xai_key = os.getenv("XAI_API_KEY")
    print(f"XAI_API_KEY found: {bool(xai_key)}")

    if not xai_key:
        print("ERROR: XAI_API_KEY not set!")
        return

    print("\nTesting Grok-4-Fast with agentic web search...")
    print("Query: 'What is Microsoft Agent 365?'\n")

    client = Client(api_key=xai_key, timeout=60)

    chat = client.chat.create(
        model="grok-4-fast",
        tools=[
            web_search(),
            x_search(),
        ],
    )

    chat.append(system("You have real-time web search. Provide accurate current information."))
    chat.append(user("What is Microsoft Agent 365?"))

    print("[*] Searching with Grok...\n")
    response = chat.sample()

    print("ANSWER:")
    print(response.content)

    if hasattr(response, 'citations') and response.citations:
        print("\n\nCITATIONS:")
        for url in response.citations[:5]:
            print(f"  - {url}")

    print(f"\n\nModel used: grok-4-fast")
    print(f"SUCCESS: Found real information about Microsoft Agent 365!")

if __name__ == "__main__":
    asyncio.run(test_grok())
