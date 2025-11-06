"""Simple status check for expert research jobs."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deepr.experts.profile import ExpertStore
from deepr.providers.openai_provider import OpenAIProvider


async def check_status(expert_name: str):
    """Check status of all research jobs for an expert."""
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert or not expert.research_jobs:
        print(f"No expert or research jobs found")
        return

    print(f"Expert: {expert_name}")
    print(f"Jobs: {len(expert.research_jobs)}")
    print()

    provider = OpenAIProvider()
    completed = 0
    in_progress = 0
    failed = 0
    total_cost = 0.0

    for i, job_id in enumerate(expert.research_jobs, 1):
        try:
            response = await provider.get_status(job_id)

            status = response.status
            if status == "completed":
                completed += 1
                icon = "[OK]"
            elif status in ["in_progress", "queued"]:
                in_progress += 1
                icon = "[>>]"
            elif status in ["failed", "cancelled"]:
                failed += 1
                icon = "[XX]"
            else:
                icon = "[??]"

            print(f"{i}. {icon} {job_id[:20]}... - {status.upper()}")

            if response.usage and response.usage.cost:
                cost = response.usage.cost
                total_cost += cost
                print(f"   Cost: ${cost:.4f}")

        except Exception as e:
            print(f"{i}. [ERR] {job_id[:20]}... - {str(e)}")
            failed += 1

    print()
    print(f"Completed: {completed}/{len(expert.research_jobs)}")
    print(f"In Progress: {in_progress}/{len(expert.research_jobs)}")
    print(f"Failed: {failed}/{len(expert.research_jobs)}")
    if total_cost > 0:
        print(f"Total cost so far: ${total_cost:.2f}")


if __name__ == "__main__":
    expert_name = sys.argv[1] if len(sys.argv) > 1 else "Agentic Digital Consciousness"
    asyncio.run(check_status(expert_name))
