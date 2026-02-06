"""Quick expert chat test - validates basic functionality.

Simple smoke test to verify expert chat works without extensive testing.
"""

import asyncio
import sys
from pathlib import Path

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepr.experts.chat import start_chat_session
from deepr.experts.profile import ExpertStore


async def quick_test():
    """Quick test: Ask expert a simple question."""
    print("\n" + "=" * 70)
    print("QUICK EXPERT CHAT TEST")
    print("=" * 70)

    # Load Midjourney Expert
    store = ExpertStore()
    expert = store.load("Midjourney Expert")

    if not expert:
        print("\n❌ Midjourney Expert not found")
        print("\nCreate it first:")
        print('  deepr expert make "Midjourney Expert" --description "Midjourney AI art" --learn --docs 1 --yes')
        return False

    print(f"\nExpert: {expert.name}")
    print(f"Documents: {expert.total_documents}")
    print(f"Domain: {expert.domain}")

    # Create session
    print("\nCreating chat session...")
    session = await start_chat_session(expert.name, budget=5.0, agentic=True)
    print("✓ Session created")

    # Ask a simple question
    query = "What are the main parameters for Midjourney?"
    print(f"\nQuery: {query}")
    print("Waiting for response...\n")

    try:
        response = await session.send_message(query, status_callback=lambda s: print(f"  {s}"))

        print("\n" + "=" * 70)
        print("RESPONSE:")
        print("=" * 70)
        print(response[:500] + "..." if len(response) > 500 else response)

        print("\n" + "=" * 70)
        print("RESULTS:")
        print("=" * 70)
        print(f"✓ Response length: {len(response)} chars")
        print(f"✓ Cost: ${session.cost_accumulated:.4f}")
        print(f"✓ Messages exchanged: {len([m for m in session.messages if m['role'] == 'user'])}")

        # Check reasoning trace
        kb_searches = len([t for t in session.reasoning_trace if t.get("step") == "search_knowledge_base"])
        web_searches = len([t for t in session.reasoning_trace if t.get("step") == "standard_research"])

        print(f"✓ Knowledge base searches: {kb_searches}")
        print(f"✓ Web searches: {web_searches}")

        # Validate response
        if len(response) > 50:
            print("\n✓ SUCCESS: Expert chat working correctly!")
            return True
        else:
            print("\n❌ FAIL: Response too short")
            return False

    except Exception as e:
        print(f"\n❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(quick_test())
    sys.exit(0 if success else 1)
