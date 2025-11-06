"""Check status of expert's research jobs directly via OpenAI API."""
import asyncio
from deepr.providers.openai_provider import OpenAIProvider
from deepr.experts.profile import ExpertStore

async def check_expert_jobs(expert_name: str):
    """Check all research jobs for an expert."""
    # Load expert
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert:
        print(f"Expert not found: {expert_name}")
        return

    if not expert.research_jobs:
        print(f"Expert has no research jobs")
        return

    print(f"Expert: {expert_name}")
    print(f"Research jobs: {len(expert.research_jobs)}")
    print(f"Budget estimated: $10.00 (5 jobs × $2.00)")
    print()

    provider = OpenAIProvider()

    completed = 0
    total_cost = 0.0

    for i, job_id in enumerate(expert.research_jobs, 1):
        try:
            response = await provider.get_status(job_id)

            status_icon = {
                "completed": "[OK]",
                "in_progress": "[>>]",
                "queued": "[ ]",
                "failed": "[X]"
            }.get(response.status, "[?]")

            print(f"{i}. [{status_icon}] {job_id[:20]}... - {response.status.upper()}")

            if response.usage and response.usage.cost:
                print(f"   Cost: ${response.usage.cost:.4f}")
                total_cost += response.usage.cost

            if response.status == "completed":
                completed += 1

        except Exception as e:
            print(f"{i}. [!] {job_id[:20]}... - Error: {e}")

    print()
    print(f"Completed: {completed}/{len(expert.research_jobs)}")
    print(f"Actual cost so far: ${total_cost:.4f}")
    print(f"Estimated: $10.00")

    if total_cost > 0:
        variance = ((total_cost - 10.0) / 10.0) * 100
        print(f"Variance: {variance:+.1f}%")

if __name__ == "__main__":
    import sys
    expert_name = sys.argv[1] if len(sys.argv) > 1 else "Agentic Digital Consciousness"
    asyncio.run(check_expert_jobs(expert_name))
