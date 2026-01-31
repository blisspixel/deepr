"""Quick script to check status of running jobs."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from deepr.providers import create_provider
from deepr.config import load_config

async def check_job(job_id: str):
    """Check job status."""
    config = load_config()
    provider = create_provider(
        config.get("provider", "openai"),
        api_key=config.get("api_key")
    )

    print(f"Checking job: {job_id}")
    response = await provider.get_status(job_id)
    print(f"\nStatus: {response.status}")
    print(f"Model: {response.model}")
    print(f"Created: {response.created_at}")
    print(f"Completed: {response.completed_at}")

    if response.status == "completed":
        print("\n=== Result ===")
        if response.output:
            for i, block in enumerate(response.output):
                print(f"\nBlock {i+1} ({block['type']}):")
                if block.get('content'):
                    for item in block['content']:
                        text = item.get('text', '')
                        print(text[:500] if len(text) > 500 else text)
        if response.usage:
            print(f"\n=== Usage ===")
            print(f"Input tokens: {response.usage.input_tokens}")
            print(f"Output tokens: {response.usage.output_tokens}")
            print(f"Total tokens: {response.usage.total_tokens}")
            print(f"Cost: ${response.usage.cost:.4f}")
    elif response.error:
        print(f"\nError: {response.error}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_job_status.py <job_id>")
        sys.exit(1)

    asyncio.run(check_job(sys.argv[1]))
