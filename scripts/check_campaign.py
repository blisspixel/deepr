"""Check campaign results from OpenAI."""
import asyncio
from deepr.providers import create_provider
from deepr.config import load_config
from pathlib import Path

async def main():
    config = load_config()
    provider = create_provider('openai', api_key=config.get('api_key'))

    # Both campaign jobs
    job_ids = [
        'resp_02aa624448173687006902998a8fb4819bac346ec5619289b2',  # task-1
        'resp_0f55dc3c1516aa68006902998b1a8481959e327f708f4123a8',  # task-2
    ]

    for i, provider_job_id in enumerate(job_ids, 1):
        print(f"\n{'='*70}")
        print(f"Campaign Task {i}")
        print('='*70)

        response = await provider.get_status(provider_job_id)

        print(f"Status: {response.status}")
        print(f"Cost: ${response.usage.cost if response.usage else 0:.4f}")

        if response.status == "completed":
            # Extract content
            content = ""
            if response.output:
                for block in response.output:
                    if block.get('type') == 'message':
                        for item in block.get('content', []):
                            if item.get('type') in ['output_text', 'text']:
                                text = item.get('text', '')
                                if text:
                                    content += text + "\n"

            print(f"Content length: {len(content)} characters")
            print(f"\nFirst 1000 characters:")
            print("-" * 70)
            print(content[:1000])
            print("-" * 70)

            # Save to file
            output_file = Path(f"campaign_task_{i}_results.md")
            output_file.write_text(content, encoding='utf-8')
            print(f"\nSaved to: {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
