"""Test script to verify knowledge base auto-update (learning) functionality."""
import asyncio
from deepr.experts.chat import start_chat_session

async def test_learning():
    """Test that expert learns from research and integrates into knowledge base."""

    print("="*70)
    print("  Testing Digital Consciousness Learning")
    print("="*70)
    print()

    # Start agentic session
    print("Starting agentic chat session...")
    session = await start_chat_session(
        "Agentic Digital Consciousness",
        budget=2.0,
        agentic=True
    )

    print(f"Expert: {session.expert.name}")
    print(f"Initial documents: {session.expert.total_documents}")
    print(f"Budget: ${session.budget:.2f}")
    print()

    # Ask a question that should trigger research
    print("Question: What is HTMX and how does it differ from React?")
    print()
    print("Expert response:")
    print("-" * 70)

    response = await session.send_message(
        "What is HTMX and how does it differ from React?"
    )

    print(response)
    print("-" * 70)
    print()

    # Check if learning occurred
    print(f"Documents after research: {session.expert.total_documents}")
    print(f"Cost accumulated: ${session.cost_accumulated:.4f}")
    print(f"Budget remaining: ${session.budget - session.cost_accumulated:.4f}")

    # Save conversation
    session_id = session.save_conversation()
    print(f"\nConversation saved: {session_id}")

    print()
    print("="*70)
    print("Test complete!")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(test_learning())
