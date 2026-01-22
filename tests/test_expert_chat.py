"""Test expert chat with Microsoft AI Expert"""
import asyncio
import sys
from pathlib import Path

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent))

from deepr.experts.profile import ExpertProfile
from deepr.experts.chat import ExpertChatSession

async def test_chat():
    print("Loading Microsoft AI Expert...")

    # Load expert profile
    expert = ExpertProfile.from_json_file("data/experts/microsoft_ai_expert.json")
    print(f"Loaded: {expert.name}")
    print(f"Documents: {expert.total_documents}")
    print()

    # Create chat session
    print("Creating chat session...")
    session = ExpertChatSession(expert, agentic=True, budget=10.0)
    print("Session created\n")

    # Test query
    query = "What is Microsoft Agent 365?"
    print(f"Query: {query}")
    print("=" * 70)

    try:
        response = await session.chat(query)
        print("\nRESPONSE:")
        print(response)
        print("\n" + "=" * 70)
        print(f"Cost: ${session.cost_accumulated:.4f}")
        print("SUCCESS!")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_chat())
    sys.exit(0 if success else 1)
