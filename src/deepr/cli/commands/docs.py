"""Docs commands - analyze documentation gaps and queue research."""

import click

from deepr.cli.async_runner import run_async_command
from deepr.cli.colors import console, print_error, print_section_header, print_success, print_warning


@click.group()
def docs():
    """Analyze documentation and queue research for gaps."""
    pass


@click.command()
@click.argument("docs_path")
@click.argument("scenario")
@click.option("--topics", "-n", default=6, type=click.IntRange(1, 10), help="Maximum research tasks to generate (1-10)")
@click.option(
    "--planner",
    "-p",
    default="gpt-5-mini",
    type=click.Choice(["gpt-5", "gpt-5-mini", "gpt-5-nano"]),
    help="GPT-5 model for analysis and planning",
)
@click.option(
    "--model",
    "-m",
    default="o4-mini-deep-research",
    type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
    help="Deep research model for execution",
)
@click.option("--execute", "-e", is_flag=True, help="Automatically execute without review")
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
    print_section_header("Documentation Gap Analysis")

    run_async_command(
        _analyze_and_queue(
            docs_path=docs_path,
            scenario=scenario,
            max_topics=topics,
            planner_model=planner,
            research_model=model,
            auto_execute=execute,
        )
    )


async def _analyze_and_queue(
    docs_path: str, scenario: str, max_topics: int, planner_model: str, research_model: str, auto_execute: bool
):
    """Execute the agentic documentation analysis workflow."""
    import asyncio
    import json
    import os
    import uuid
    from pathlib import Path

    from deepr.config import load_config
    from deepr.providers.base import ResearchRequest, ToolConfig
    from deepr.providers.openai_provider import OpenAIProvider
    from deepr.queue.base import JobStatus, ResearchJob
    from deepr.queue.local_queue import SQLiteQueue
    from deepr.services.doc_reviewer import DocReviewer
    from deepr.services.research_planner import ResearchPlanner

    try:
        # Validate path (non-blocking exists check)
        docs_dir = Path(docs_path)
        if not await asyncio.to_thread(docs_dir.exists):
            print_error(f"Path not found: {docs_path}")
            raise click.Abort()

        console.print(f"\nDocs location: {docs_dir}")
        console.print(f"Scenario: {scenario}")
        console.print(f"Max research tasks: {max_topics}\n")

        if not auto_execute:
            click.confirm(
                "Run metered document review and research planning? Both calls are budget-gated.",
                abort=True,
            )

        # Step 1: Scan and analyze docs with GPT-5
        console.print("Step 1: Analyzing existing documentation...")
        reviewer = DocReviewer(model=planner_model, docs_path=str(docs_dir))

        analysis = reviewer.review_docs(scenario=scenario)

        relevant = [*analysis.get("sufficient", []), *analysis.get("needs_update", [])]
        gaps = analysis.get("gaps", [])

        if relevant:
            print_success(f"Found {len(relevant)} relevant docs")
            for doc in relevant[:5]:
                quality = doc.get("quality", "unknown") if isinstance(doc, dict) else "unknown"
                doc_path = str(doc.get("path") or doc.get("name") or "document") if isinstance(doc, dict) else str(doc)
                console.print(f"  - {Path(doc_path).name} ({quality})")
            if len(relevant) > 5:
                console.print(f"  ... and {len(relevant) - 5} more")

        if gaps:
            print_success(f"Identified {len(gaps)} gaps")
            for gap in gaps[:3]:
                console.print(f"  - {gap}")
            if len(gaps) > 3:
                console.print(f"  ... and {len(gaps) - 3} more")

        # Step 2: Generate research plan with GPT-5
        console.print("\nStep 2: Generating research plan...")

        context = json.dumps(analysis, sort_keys=True)

        planner = ResearchPlanner(model=planner_model)
        tasks = planner.plan_research(scenario=scenario, max_tasks=max_topics, context=context)

        if not tasks:
            print_error("No research tasks generated")
            raise click.Abort()

        print_success(f"Generated {len(tasks)} research tasks:")
        console.print()

        for i, task in enumerate(tasks, 1):
            task_type = task.get("type", "analysis")
            console.print(f"{i}. {task['title']} ({task_type})")
            console.print(f"   {task['prompt'][:80]}...")
            console.print()

        # Calculate cost estimate
        avg_cost = 0.5 if "mini" in research_model else 5.0
        doc_count = sum(1 for t in tasks if t.get("type") == "documentation")
        analysis_count = len(tasks) - doc_count

        est_cost = (doc_count * avg_cost * 0.7) + (analysis_count * avg_cost)

        console.print(f"Estimated cost: ${est_cost:.2f}")
        console.print(f"Estimated time: {len(tasks) * 10} minutes\n")

        # Step 3: Confirmation
        if not auto_execute:
            if not click.confirm(f"Submit {len(tasks)} research jobs?"):
                print_warning("Cancelled")
                return

        # Step 4: Submit jobs
        console.print("\nStep 3: Submitting research jobs...")

        config = load_config()
        queue_path = Path(str(config["queue_db_path"]))
        await asyncio.to_thread(queue_path.parent.mkdir, parents=True, exist_ok=True)
        queue = SQLiteQueue(str(queue_path))
        provider = None

        from deepr.experts.research_cost_gate import refund_research_cost, reserve_configured_research_cost
        from deepr.services.research_cost_reconciliation import reconcile_research_cost_reservations
        from deepr.services.research_submission import dispatch_reserved_research

        job_ids = []

        for i, task in enumerate(tasks, 1):
            # Use task-specific model if specified, otherwise use default
            task_model = task.get("model", research_model)
            task_type = task.get("type", "analysis")

            # Create job
            job_id = str(uuid.uuid4())
            await reconcile_research_cost_reservations(queue, default_provider="openai")
            _, reservation = reserve_configured_research_cost(
                job_id=job_id,
                provider="openai",
                prompt=task["prompt"],
                model=task_model,
                enable_web_search=True,
            )
            if provider is None:
                try:
                    provider = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))
                except Exception:
                    refund_research_cost(reservation)
                    raise
            job = ResearchJob(
                id=job_id,
                prompt=task["prompt"],
                model=task_model,
                enable_web_search=True,
                status=JobStatus.QUEUED,
                metadata={
                    "title": task["title"],
                    "type": task_type,
                    "model": task_model,
                    "scenario": scenario,
                    "docs_path": str(docs_dir),
                    "batch_id": f"docs_analysis_{uuid.uuid4().hex[:8]}",
                    **reservation.metadata(),
                },
            )

            # Submit to provider
            request = ResearchRequest(
                prompt=task["prompt"],
                model=task_model,
                system_message="You are a technical documentation expert. Research and document best practices, implementation patterns, and practical guidance.",
                tools=[ToolConfig(type="web_search_preview")],
                background=True,
            )

            await dispatch_reserved_research(
                queue=queue,
                provider=provider,
                job=job,
                request=request,
                reservation=reservation,
            )

            job_ids.append(job_id)
            model_label = "o3" if "o3" in task_model else "o4-mini"
            console.print(f"  [{i}/{len(tasks)}] {task['title']} ({model_label}, {task_type})")

        print_success(f"Submitted {len(job_ids)} research jobs!")
        console.print("\nMonitor with:")
        console.print("  deepr queue list")
        console.print("  deepr queue stats")
        console.print("\nView results when complete:")
        console.print("  deepr research result <job-id>")

    except Exception as e:
        print_error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        raise click.Abort()


docs.add_command(analyze)
