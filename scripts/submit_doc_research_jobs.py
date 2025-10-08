"""
Submit research jobs for identified documentation gaps.
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from deepr.queue.local_queue import SQLiteQueue
from deepr.storage.local import LocalStorage
from deepr.providers.openai_provider import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.queue.base import ResearchJob, JobStatus
from datetime import datetime
import uuid

load_dotenv()

# Research prompts for top 6 gaps identified by GPT-5
RESEARCH_TASKS = [
    {
        "title": "Multi-Provider Orchestration Patterns",
        "prompt": """Document multi-provider orchestration and abstraction layer patterns for research automation platforms.

Cover:
- Provider adapter patterns (OpenAI, Azure OpenAI, Anthropic)
- Interface contracts and unified SDK design
- Capability discovery and feature detection
- Fallback strategies and provider selection
- Implementation examples with code patterns
- Best practices for provider-agnostic design

Focus on practical implementation guidance for 2025."""
    },
    {
        "title": "Context Chaining and State Management",
        "prompt": """Document context chaining and cross-phase state management for multi-step research workflows.

Cover:
- Data models for context representation
- Persistence strategies (what to store, where, how long)
- Context summarization and compression techniques
- Merging and conflict resolution across phases
- Examples showing context flow between tasks
- Versioning and TTL strategies

Focus on production-ready approaches for agentic systems."""
    },
    {
        "title": "Task Routing and Cost-Optimized Scheduling",
        "prompt": """Document task routing, queue-based scheduling, and cost-optimized task mix strategies.

Cover:
- Intelligent routing algorithms (documentation vs analysis tasks)
- Queue priority and worker assignment
- Concurrency limits and backoff/retry policies
- Cost-aware model selection (o4-mini vs o3 vs Claude)
- SLA-aware scheduling
- Batching and fanout patterns

Focus on operational best practices for 2025."""
    },
    {
        "title": "Intelligent Document Reuse and Knowledge Store",
        "prompt": """Document intelligent document reuse and knowledge-store integration for research platforms.

Cover:
- Document indexing and retrieval strategies
- Vector store integration (when to use, which ones)
- Metadata schema and relevance ranking
- Deduplication and versioning approaches
- Refresh/update pipelines (when to reuse vs re-fetch)
- Implementation examples

Focus on cost-effective doc management for 2025."""
    },
    {
        "title": "CLI Interface and Developer Workflows",
        "prompt": """Document CLI interface design and developer workflows for research automation platforms.

Cover:
- CLI command patterns and best practices
- Configuration file schemas (.env, config files)
- Authentication flows (multiple providers)
- Local development workflows
- Sample projects and common operations
- Debugging and troubleshooting guides

Focus on developer UX for 2025."""
    },
    {
        "title": "Observability, Metrics, and Provider Fallback",
        "prompt": """Document observability, metrics, billing, and provider fallback strategies for multi-provider research systems.

Cover:
- Telemetry and progress tracking
- Cost tracking per task/campaign/provider
- Error diagnostics and alerting
- End-to-end traces for task execution
- Automated fallback when providers fail
- Budget management and cost controls

Focus on production operations for 2025."""
    },
]

async def main():
    # Initialize services
    config_path = Path('.deepr')
    config_path.mkdir(exist_ok=True)

    queue = SQLiteQueue(str(config_path / 'queue.db'))
    storage = LocalStorage(str(config_path / 'storage'))
    provider = OpenAIProvider(api_key=os.getenv('OPENAI_API_KEY'))

    print(f'Submitting {len(RESEARCH_TASKS)} research jobs...\n')

    job_ids = []

    for i, task in enumerate(RESEARCH_TASKS, 1):
        print(f'{i}. {task["title"]}')

        # Create job
        job_id = str(uuid.uuid4())
        job = ResearchJob(
            id=job_id,
            prompt=task['prompt'],
            model='o4-mini-deep-research',
            enable_web_search=True,
            status=JobStatus.QUEUED,
            metadata={
                'title': task['title'],
                'purpose': 'documentation_gap',
                'batch_id': 'doc_gaps_batch_1'
            }
        )

        # Enqueue
        await queue.enqueue(job)

        # Submit to provider
        request = ResearchRequest(
            prompt=task['prompt'],
            model='o4-mini-deep-research',
            system_message='You are a technical documentation expert. Research and document best practices, implementation patterns, and practical guidance.',
            tools=[ToolConfig(type='web_search_preview')],
            background=True,
        )

        provider_job_id = await provider.submit_research(request)

        # Update with provider job ID
        await queue.update_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            provider_job_id=provider_job_id,
        )

        job_ids.append({'local_id': job_id, 'provider_id': provider_job_id, 'title': task['title']})
        print(f'   Job ID: {job_id[:8]}...')
        print(f'   Provider ID: {provider_job_id}')
        print()

    print(f'\n[OK] Submitted {len(job_ids)} research jobs!')
    print(f'\nEstimated cost: ${len(job_ids) * 0.5:.2f} - ${len(job_ids) * 2:.2f}')
    print(f'Estimated time: {len(job_ids) * 10} - {len(job_ids) * 20} minutes\n')

    # Save job list
    output_file = Path('.deepr/doc_research_jobs.txt')
    with open(output_file, 'w') as f:
        for job in job_ids:
            f.write(f'{job["local_id"]}\t{job["provider_id"]}\t{job["title"]}\n')

    print(f'Job IDs saved to {output_file}')
    print(f'\nMonitor with: python scripts/monitor_research_jobs.py')

if __name__ == '__main__':
    asyncio.run(main())
