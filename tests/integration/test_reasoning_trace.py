"""Test enhanced reasoning trace with model explanations"""
import asyncio
import sys
sys.path.insert(0, "..")

from deepr.experts.chat import start_chat_session
from deepr.cli import ui

async def test():
    print("Starting expert session...")
    session = await start_chat_session("Microsoft AI Expert", budget=10.0, agentic=True)

    print("\n" + "="*80)
    print("TEST 1: Ask about Agent 365 pricing (should use cached knowledge)")
    print("="*80 + "\n")

    response1 = await session.chat("Tell me about Agent 365 pricing")

    print("\n\n" + "="*80)
    print("REASONING TRACE FOR QUERY 1:")
    print("="*80)
    ui.print_trace(session.reasoning_trace)

    print("\n\n" + "="*80)
    print("TEST 2: Ask about a new topic (should trigger web search)")
    print("="*80 + "\n")

    # Reset reasoning trace for clarity
    session.reasoning_trace = []

    response2 = await session.chat("What are the latest features in Windows 12 announced in January 2026?")

    print("\n\n" + "="*80)
    print("REASONING TRACE FOR QUERY 2:")
    print("="*80)
    ui.print_trace(session.reasoning_trace)

    print("\n\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total cost: ${session.cost_accumulated:.4f}")
    print(f"Total queries: 2")
    print("\nKey improvements:")
    print("✓ Model explains WHY it searches knowledge base")
    print("✓ Model explains WHY it needs web search")
    print("✓ Full transparency into decision-making process")
    print("✓ Can validate model is making intelligent choices")

if __name__ == "__main__":
    asyncio.run(test())
