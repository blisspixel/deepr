"""Inspect the actual research output to verify quality."""
import asyncio
from deepr.providers.openai_provider import OpenAIProvider
from deepr.experts.profile import ExpertStore

async def inspect_research(expert_name: str):
    """Inspect research output quality."""
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert or not expert.research_jobs:
        print("No research jobs found")
        return

    provider = OpenAIProvider()

    # Check first job in detail
    job_id = expert.research_jobs[0]
    print(f"Inspecting: {job_id}")
    print()

    response = await provider.get_status(job_id)

    print(f"Status: {response.status}")
    print(f"Model: {response.model}")
    print()

    if response.usage:
        print(f"Input tokens: {response.usage.input_tokens:,}")
        print(f"Output tokens: {response.usage.output_tokens:,}")
        print(f"Reasoning tokens: {response.usage.reasoning_tokens:,}")
        print(f"Total tokens: {response.usage.total_tokens:,}")
        print(f"Cost: ${response.usage.cost:.4f}")
        print()

    # Check output structure
    if response.output:
        print(f"Output blocks: {len(response.output)}")

        # Count different block types
        from collections import Counter
        block_types = Counter(block.get('type') for block in response.output)
        print(f"Block types: {dict(block_types)}")
        print()

        # Show first few blocks
        print("First 5 blocks:")
        for i, block in enumerate(response.output[:5], 1):
            block_type = block.get('type')
            print(f"{i}. {block_type}")

            # Show details for different types
            if block_type == 'web_search_call':
                action = block.get('action', {})
                print(f"   Action: {action.get('type')}")
                if action.get('type') == 'search':
                    print(f"   Query: {action.get('query', '')[:60]}...")
            elif block_type == 'reasoning':
                summary = block.get('summary', [])
                if summary:
                    text = summary[0].get('text', '')[:100]
                    print(f"   Summary: {text}...")
            elif block_type == 'message':
                content = block.get('content', [])
                if content:
                    text = content[0].get('text', '')[:150]
                    print(f"   Text: {text}...")

        # Extract final message
        print("\n" + "="*70)
        print("Final Report (first 500 chars):")
        print("="*70)
        for block in response.output:
            if block.get('type') == 'message':
                for item in block.get('content', []):
                    if item.get('type') in ['output_text', 'text']:
                        text = item.get('text', '')
                        print(text[:500])
                        print("\n[... truncated ...]")
                        print(f"\nTotal length: {len(text):,} characters")
                        return

if __name__ == "__main__":
    import sys
    expert_name = sys.argv[1] if len(sys.argv) > 1 else "Agentic Digital Consciousness"
    asyncio.run(inspect_research(expert_name))
