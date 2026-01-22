"""Simple test of knowledge base search"""
import asyncio
import sys
sys.path.insert(0, ".")

from deepr.experts.chat import ExpertChatSession, start_chat_session

async def test():
    print("Starting session...")
    session = await start_chat_session("Microsoft AI Expert", budget=10.0, agentic=True)

    print("\nTesting search...")
    results = await session._search_knowledge_base("Agent 365 pricing", top_k=5)

    print(f"\nResults: {len(results)} found")
    for i, result in enumerate(results):
        print(f"\n{i+1}. {result.get('filename', 'unknown')}")
        print(f"   Content preview: {result.get('content', '')[:200]}...")

if __name__ == "__main__":
    asyncio.run(test())
