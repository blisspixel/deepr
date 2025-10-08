"""Docs commands - analyze documentation gaps and queue research."""

import click
from typing import Optional
from deepr.branding import print_section_header, CHECK, CROSS


@click.group()
def docs():
    """Analyze documentation and queue research for gaps."""
    pass


@click.command()
@click.argument("docs_path")
@click.argument("scenario")
@click.option("--topics", "-n", default=6, type=click.IntRange(1, 10),
              help="Maximum research tasks to generate (1-10)")
@click.option("--planner", "-p", default="gpt-5-mini",
              type=click.Choice(["gpt-5", "gpt-5-mini", "gpt-5-nano"]),
              help="GPT-5 model for analysis and planning")
@click.option("--model", "-m", default="o4-mini-deep-research",
              type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
              help="Deep research model for execution")
@click.option("--execute", "-e", is_flag=True,
              help="Automatically execute without review")
def analyze(docs_path: str, scenario: str, topics: int, planner: str, model: str, execute: bool):
    """
    Analyze documentation gaps and queue research to fill them.

    Agentic workflow:
    1. Scan docs at given path
    2. Use GPT-5 to analyze what's missing for the scenario
    3. Generate research plan to fill gaps
    4. Submit research jobs (after user approval unless --execute)

    Examples:
        deepr docs analyze "docs/research and documentation" "Building Deepr" --topics 6
        deepr docs analyze "./my-docs" "React best practices 2025" --execute
        deepr docs analyze "C:/project/docs" "AI safety guidelines" -n 8
    """
    print_section_header(f"Documentation Gap Analysis")

    import asyncio
    asyncio.run(_analyze_and_queue(
        docs_path=docs_path,
        scenario=scenario,
        max_topics=topics,
        planner_model=planner,
        research_model=model,
        auto_execute=execute
    ))


async def _analyze_and_queue(
    docs_path: str,
    scenario: str,
    max_topics: int,
    planner_model: str,
    research_model: str,
    auto_execute: bool
):
    """Execute the agentic documentation analysis workflow."""
    import os
    import json
    from pathlib import Path
    from deepr.services.doc_reviewer import DocReviewer
    from deepr.services.research_planner import ResearchPlanner
    from deepr.queue.local_queue import SQLiteQueue
    from deepr.storage.local import LocalStorage
    from deepr.providers.openai_provider import OpenAIProvider
    from deepr.providers.base import ResearchRequest, ToolConfig
    from deepr.queue.base import ResearchJob, JobStatus
    import uuid

    try:
        # Validate path
        docs_dir = Path(docs_path)
        if not docs_dir.exists():
            click.echo(f"\n{CROSS} Path not found: {docs_path}", err=True)
            raise click.Abort()

        click.echo(f"\nDocs location: {docs_dir}")
        click.echo(f"Scenario: {scenario}")
        click.echo(f"Max research tasks: {max_topics}\n")

        # Step 1: Scan and analyze docs with GPT-5
        click.echo("Step 1: Analyzing existing documentation...")
        reviewer = DocReviewer(model=planner_model)

        analysis = reviewer.check_existing_docs(
            scenario=scenario,
            docs_dir=str(docs_dir)
        )

        relevant = analysis.get('relevant_docs', [])
        gaps = analysis.get('gaps', [])

        if relevant:
            click.echo(f"\n{CHECK} Found {len(relevant)} relevant docs")
            for doc in relevant[:5]:
                quality = doc.get('quality', 'unknown')
                click.echo(f"  - {Path(doc['path']).name} ({quality})")
            if len(relevant) > 5:
                click.echo(f"  ... and {len(relevant) - 5} more")

        if gaps:
            click.echo(f"\n{CHECK} Identified {len(gaps)} gaps")
            for gap in gaps[:3]:
                click.echo(f"  - {gap}")
            if len(gaps) > 3:
                click.echo(f"  ... and {len(gaps) - 3} more")

        # Step 2: Generate research plan with GPT-5
        click.echo(f"\nStep 2: Generating research plan...")

        context = reviewer.generate_enhanced_plan_context(scenario, analysis)

        planner = ResearchPlanner(model=planner_model)
        tasks = planner.plan_research(
            scenario=scenario,
            max_tasks=max_topics,
            context=context
        )

        if not tasks:
            click.echo(f"\n{CROSS} No research tasks generated", err=True)
            raise click.Abort()

        click.echo(f"\n{CHECK} Generated {len(tasks)} research tasks:\n")

        for i, task in enumerate(tasks, 1):
            task_type = task.get('type', 'analysis')
            click.echo(f"{i}. {task['title']} ({task_type})")
            click.echo(f"   {task['prompt'][:80]}...")
            click.echo()

        # Calculate cost estimate
        avg_cost = 0.5 if 'mini' in research_model else 5.0
        doc_count = sum(1 for t in tasks if t.get('type') == 'documentation')
        analysis_count = len(tasks) - doc_count

        est_cost = (doc_count * avg_cost * 0.7) + (analysis_count * avg_cost)

        click.echo(f"Estimated cost: ${est_cost:.2f}")
        click.echo(f"Estimated time: {len(tasks) * 10} minutes\n")

        # Step 3: Confirmation
        if not auto_execute:
            if not click.confirm(f"Submit {len(tasks)} research jobs?"):
                click.echo(f"\n{CROSS} Cancelled")
                return

        # Step 4: Submit jobs
        click.echo(f"\nStep 3: Submitting research jobs...")

        # Initialize services
        config_path = Path('.deepr')
        config_path.mkdir(exist_ok=True)

        queue = SQLiteQueue(str(config_path / 'queue.db'))
        storage = LocalStorage(str(config_path / 'storage'))
        provider = OpenAIProvider(api_key=os.getenv('OPENAI_API_KEY'))

        job_ids = []

        for i, task in enumerate(tasks, 1):
            # Use task-specific model if specified, otherwise use default
            task_model = task.get('model', research_model)
            task_type = task.get('type', 'analysis')

            # Create job
            job_id = str(uuid.uuid4())
            job = ResearchJob(
                id=job_id,
                prompt=task['prompt'],
                model=task_model,
                enable_web_search=True,
                status=JobStatus.QUEUED,
                metadata={
                    'title': task['title'],
                    'type': task_type,
                    'model': task_model,
                    'scenario': scenario,
                    'docs_path': str(docs_dir),
                    'batch_id': f'docs_analysis_{uuid.uuid4().hex[:8]}'
                }
            )

            await queue.enqueue(job)

            # Submit to provider
            request = ResearchRequest(
                prompt=task['prompt'],
                model=task_model,
                system_message='You are a technical documentation expert. Research and document best practices, implementation patterns, and practical guidance.',
                tools=[ToolConfig(type='web_search_preview')],
                background=True,
            )

            provider_job_id = await provider.submit_research(request)

            # Update status
            await queue.update_status(
                job_id=job_id,
                status=JobStatus.PROCESSING,
                provider_job_id=provider_job_id,
            )

            job_ids.append(job_id)
            model_label = "o3" if "o3" in task_model else "o4-mini"
            click.echo(f"  [{i}/{len(tasks)}] {task['title']} ({model_label}, {task_type})")

        click.echo(f"\n{CHECK} Submitted {len(job_ids)} research jobs!")
        click.echo(f"\nMonitor with:")
        click.echo(f"  deepr queue list")
        click.echo(f"  deepr queue stats")
        click.echo(f"\nView results when complete:")
        click.echo(f"  deepr research result <job-id>")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


docs.add_command(analyze)
