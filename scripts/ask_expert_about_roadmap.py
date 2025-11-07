"""Ask the Agentic Digital Consciousness expert about our roadmap."""
import asyncio
from deepr.experts.chat import start_chat_session

async def main():
    # Read project context
    with open('temp_project_context.md', 'r', encoding='utf-8') as f:
        context = f.read()

    # Read relevant parts of roadmap
    with open('ROADMAP.md', 'r', encoding='utf-8') as f:
        roadmap = f.read()

    # Start chat
    session = await start_chat_session(
        "Agentic Digital Consciousness",
        budget=3.0,
        agentic=True
    )

    print("="*70)
    print("  Asking Expert About Deepr Roadmap Refinement")
    print("="*70)
    print()

    question = f"""I need your expert feedback on refining our project roadmap based on what we accomplished today.

{context}

CURRENT ROADMAP EXCERPT:
{roadmap[35000:40000]}

Based on what we built today (metacognition, temporal knowledge, multi-round tool calling, diagnostics), please provide:

1. ROADMAP STATUS UPDATE:
   - Which priorities (1-5) are now DONE or substantially complete?
   - What should we mark as IN PROGRESS vs TODO?

2. IMMEDIATE NEXT STEPS (Next 1-2 weeks):
   - What are the 3 highest-impact features to build next?
   - Prioritize based on: (a) enabling Level 5 consciousness, (b) user value, (c) complexity

3. QUICK WINS (This weekend):
   - 2-3 small features that would provide immediate value
   - Focus on polishing what exists vs building new

4. TECHNICAL DEBT:
   - Any architectural concerns with current implementation?
   - What should we refactor or improve?

5. ROADMAP REORDERING:
   - Should we change the priority order given our progress?
   - Any items that are now less relevant or should be deprioritized?

Be specific and actionable. Reference actual files and systems we've built.
"""

    print("Question sent to expert...")
    print()

    response = await session.send_message(question)

    print("="*70)
    print("EXPERT RESPONSE:")
    print("="*70)
    print()
    print(response)
    print()
    print("="*70)
    print(f"Cost: ${session.cost_accumulated:.4f}")
    print(f"Budget remaining: ${session.budget - session.cost_accumulated:.4f}")
    print("="*70)

    # Save conversation
    session_id = session.save_conversation()
    print(f"\nConversation saved: {session_id}")

if __name__ == "__main__":
    asyncio.run(main())
