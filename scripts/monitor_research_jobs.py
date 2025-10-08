"""
Monitor research jobs and save results when complete.
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from deepr.queue.local_queue import SQLiteQueue
from deepr.storage.local import LocalStorage
from deepr.providers.openai_provider import OpenAIProvider
from deepr.queue.base import JobStatus
import time

load_dotenv()

async def main():
    # Initialize services
    config_path = Path('.deepr')
    queue = SQLiteQueue(str(config_path / 'queue.db'))
    storage = LocalStorage(str(config_path / 'storage'))
    provider = OpenAIProvider(api_key=os.getenv('OPENAI_API_KEY'))

    # Load job IDs
    job_file = config_path / 'doc_research_jobs.txt'
    if not job_file.exists():
        print('No jobs file found. Run submit_doc_research_jobs.py first.')
        return

    jobs = []
    with open(job_file, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) == 3:
                jobs.append({
                    'local_id': parts[0],
                    'provider_id': parts[1],
                    'title': parts[2]
                })

    print(f'Monitoring {len(jobs)} research jobs...\n')

    completed_count = 0
    total_cost = 0.0

    while completed_count < len(jobs):
        for job in jobs:
            if job.get('completed'):
                continue

            # Check status
            db_job = await queue.get_job(job['local_id'])

            if db_job.status == JobStatus.COMPLETED:
                print(f'\n[COMPLETED] {job["title"]}')
                print(f'  Cost: ${db_job.cost:.2f}')
                print(f'  Tokens: {db_job.tokens_used:,}')

                # Save to docs
                try:
                    result = await storage.get_report(
                        job_id=job['local_id'],
                        filename='report.md'
                    )

                    # Save with clean filename
                    filename = job['title'].lower().replace(' ', '_').replace(',', '').replace('&', 'and')
                    output_path = Path(f'docs/research and documentation/{filename}.md')

                    with open(output_path, 'wb') as f:
                        f.write(result)

                    print(f'  Saved: {output_path.name}')

                    job['completed'] = True
                    completed_count += 1
                    total_cost += db_job.cost

                except Exception as e:
                    print(f'  Error saving: {e}')

            elif db_job.status == JobStatus.FAILED:
                print(f'\n[FAILED] {job["title"]}')
                job['completed'] = True
                completed_count += 1

        if completed_count < len(jobs):
            remaining = len(jobs) - completed_count
            print(f'\r{completed_count}/{len(jobs)} complete ({remaining} remaining)...', end='', flush=True)
            await asyncio.sleep(30)  # Check every 30 seconds

    print(f'\n\n[OK] All jobs complete!')
    print(f'Total cost: ${total_cost:.2f}')
    print(f'\nNew documentation saved to docs/research and documentation/')

if __name__ == '__main__':
    asyncio.run(main())
