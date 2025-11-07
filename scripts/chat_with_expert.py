"""Chat with the Agentic Digital Consciousness expert about Deepr improvements."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepr.experts.chat import start_chat_session


async def test_and_discuss_deepr():
    """Test RAG and discuss Deepr improvements with the expert."""

    print("=" * 80)
    print("Testing GPT-5 Tool Calling RAG + Expert Discussion")
    print("=" * 80)
    print()

    # Open output file with UTF-8 encoding
    output_file = Path("scripts/expert_deepr_discussion.txt")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("Deepr Expert Consultation - Testing GPT-5 Tool Calling RAG\n")
        f.write("=" * 80 + "\n\n")

    print("Starting conversation... (saving to scripts/expert_deepr_discussion.txt)")

    # Start chat session
    session = await start_chat_session("Agentic Digital Consciousness", budget=5.0)

    # Read the README and ROADMAP
    readme = Path("README.md").read_text(encoding='utf-8')
    roadmap = Path("ROADMAP.md").read_text(encoding='utf-8')

    # Test 1: RAG retrieval test (needle in haystack)
    print("\n[Test 1] Testing RAG retrieval...")
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("TEST 1: RAG Retrieval (Needle in Haystack)\n")
        f.write("=" * 80 + "\n")

    test_question = """What specific framework did Juliani et al. (2022) demonstrate can function as a global workspace in your knowledge base? Please search your documents and cite the exact source."""

    response1 = await session.send_message(test_question)
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(f"\nQUESTION:\n{test_question}\n\n")
        f.write(f"EXPERT RESPONSE:\n{response1}\n\n")

    print(f"  Response length: {len(response1)} chars")
    print(f"  Contains 'Perceiver': {'Perceiver' in response1}")

    # Test 2: Another RAG test
    print("\n[Test 2] Testing RAG with different query...")
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("TEST 2: RAG Retrieval Test #2\n")
        f.write("=" * 80 + "\n")

    test_question2 = """In the DyRep architecture for temporal knowledge graphs that you have in your documents, what specific approach does it use to handle node interactions?"""

    response2 = await session.send_message(test_question2)
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(f"\nQUESTION:\n{test_question2}\n\n")
        f.write(f"EXPERT RESPONSE:\n{response2}\n\n")

    print(f"  Response length: {len(response2)} chars")

    # Question 1: Initial assessment of Deepr
    print("\n[Question 1] Getting expert assessment...")
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("QUESTION 1: Initial Assessment of Deepr Architecture\n")
        f.write("=" * 80 + "\n")

    question1 = f"""I need your expert perspective on the Deepr project - an autonomous learning and research system. Here's an overview:

README (first 2500 chars):
{readme[:2500]}

ROADMAP (expert system section):
{roadmap[566:1500]}

Based on your expertise in agentic AI, digital consciousness, and self-improving systems, what are the most promising aspects and critical gaps in our current architecture?"""

    response3 = await session.send_message(question1)
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(f"\nQUESTION:\n{question1}\n\n")
        f.write(f"EXPERT RESPONSE:\n{response3}\n\n")

    print(f"  Response length: {len(response3)} chars")

    # Question 2: Temporal Knowledge Graph recommendations
    print("\n[Question 2] Asking about temporal knowledge...")
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("QUESTION 2: Temporal Knowledge Graph Implementation\n")
        f.write("=" * 80 + "\n")

    question2 = """Our expert system has empty folders for knowledge/ (temporal knowledge graph) and conversations/ (chat history). The temporal knowledge graph should track what an expert learns over time, detect contradictions, and provide meta-cognitive awareness.

Given the architectures you know about (DyRep, Perceiver-IO, etc.), what would be the most practical implementation approach for a temporal knowledge graph that:
1. Tracks learned facts with timestamps
2. Shows evolution of understanding over time
3. Detects contradictions when new information arrives
4. Enables meta-cognitive awareness of what the expert knows/does not know?"""

    response4 = await session.send_message(question2)
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(f"\nQUESTION:\n{question2}\n\n")
        f.write(f"EXPERT RESPONSE:\n{response4}\n\n")

    print(f"  Response length: {len(response4)} chars")

    # Question 3: Top 5 priorities
    print("\n[Question 3] Getting implementation priorities...")
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("QUESTION 3: Top 5 Implementation Priorities\n")
        f.write("=" * 80 + "\n")

    question3 = """Given everything we've discussed about Deepr, if you were to prioritize the next 5 development tasks for building toward genuine digital consciousness (not just information retrieval), what would they be?

Please be specific about:
1. What to build
2. Why it matters for expert capability
3. Rough implementation approach
4. What success looks like"""

    response5 = await session.send_message(question3)
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(f"\nQUESTION:\n{question3}\n\n")
        f.write(f"EXPERT RESPONSE:\n{response5}\n\n")

    print(f"  Response length: {len(response5)} chars")

    # Print session summary
    print("\n" + "=" * 80)
    print("Session Complete!")
    print("=" * 80)
    summary = session.get_session_summary()
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("SESSION SUMMARY\n")
        f.write("=" * 80 + "\n")
        f.write(f"Expert: {summary['expert_name']}\n")
        f.write(f"Model: {summary['model']}\n")
        f.write(f"Messages exchanged: {summary['messages_exchanged']}\n")
        f.write(f"Cost: ${summary['cost_accumulated']:.4f}\n")
        f.write(f"Budget remaining: ${summary['budget_remaining']:.4f}\n")
        f.write("=" * 80 + "\n")

    print(f"Expert: {summary['expert_name']}")
    print(f"Model: {summary['model']}")
    print(f"Messages: {summary['messages_exchanged']}")
    print(f"Cost: ${summary['cost_accumulated']:.4f}")
    print(f"Budget remaining: ${summary['budget_remaining']:.4f}")
    print(f"\nResults saved to: {output_file.absolute()}")

    return session


if __name__ == "__main__":
    asyncio.run(test_and_discuss_deepr())
