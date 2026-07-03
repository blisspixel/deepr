"""Expert system commands - create, manage, and interact with domain experts."""

import asyncio
from datetime import UTC, datetime

import click

from deepr.cli.colors import (
    console,
    print_error,
    print_header,
    print_key_value,
    print_list_item,
    print_section_header,
    print_success,
    print_warning,
)


@click.group(invoke_without_command=True)
@click.option("--list", "list_flag", "-l", is_flag=True, help="List all experts")
@click.pass_context
def expert(ctx, list_flag):
    """Create and interact with domain experts.

    Experts combine knowledge bases with agentic research capabilities.
    They can autonomously research when they encounter knowledge gaps.

    COMMON COMMANDS:
      deepr expert list              List all experts
      deepr expert make "Name"       Create a new expert
      deepr expert info "Name"       Show expert details
      deepr chat expert "Name"       Chat with an expert

    EXAMPLES:
      # List all experts
      deepr expert list
      deepr expert --list

      # Create expert from documents
      deepr expert make "Python Expert" -f docs/*.md

      # Get expert details
      deepr expert info "Python Expert"

      # Chat with expert
      deepr chat expert "Python Expert" --message "What are decorators?"
    """
    # If --list flag is used, invoke list command
    if list_flag:
        ctx.invoke(list_experts)
    # If no subcommand provided, show help
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@expert.command(name="make")
@click.argument("name")
@click.option(
    "--files", "-f", multiple=True, type=click.Path(exists=True), help="Files to include in expert's knowledge base"
)
@click.option("--description", "-d", help="Description of expert's domain")
@click.option(
    "--provider",
    "-p",
    default="openai",
    type=click.Choice(["openai", "azure", "gemini"]),
    help="AI provider for expert",
)
@click.option("--local", is_flag=True, default=False, help="Create a local-only expert profile without provider setup")
@click.option("--local-model", default=None, help="Local model name to record for local maintenance")
@click.option("--learn", is_flag=True, default=False, help="Generate and execute autonomous learning curriculum")
@click.option("--budget", type=float, default=None, help="Budget limit for autonomous learning (requires --learn)")
@click.option(
    "--topics", type=int, default=None, help="Total number of topics (auto-calculated if using --docs/--quick/--deep)"
)
@click.option("--docs", type=int, default=None, help="Number of documentation topics (FOCUS, ~$0.25 each)")
@click.option("--quick", type=int, default=None, help="Number of quick research topics (FOCUS, ~$0.25 each)")
@click.option("--deep", type=int, default=None, help="Number of deep research topics (CAMPAIGN, ~$2.00 each)")
@click.option(
    "--no-discovery", is_flag=True, default=False, help="Skip source discovery phase (faster but less comprehensive)"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation for autonomous learning")
@click.option("--confirm-metered-profile", is_flag=True, help="Allow --yes for reviewed API profile setup.")
def make_expert(
    name: str,
    files: tuple,
    description: str | None,
    provider: str,
    local: bool,
    local_model: str | None,
    learn: bool,
    budget: float | None,
    topics: int | None,
    docs: int | None,
    quick: int | None,
    deep: int | None,
    no_discovery: bool,
    yes: bool,
    confirm_metered_profile: bool,
):
    """Create a new domain expert with a knowledge base."""
    import asyncio

    from deepr.cli.validation import validate_budget, validate_expert_name, validate_upload_files

    try:
        name = validate_expert_name(name)
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    if files:
        try:
            files = tuple(str(f) for f in validate_upload_files(files))
        except click.UsageError as e:
            click.echo(f"Error: {e}", err=True)
            return

    if local:
        from deepr.cli.commands.semantic.local_expert import make_local_expert_profile

        learning_options_used = (
            learn or no_discovery or any(value is not None for value in (budget, topics, docs, quick, deep))
        )
        make_local_expert_profile(
            name=name,
            files=files,
            description=description,
            local_model=local_model,
            learning_options_used=learning_options_used,
        )
        return

    if budget is not None and not yes:
        try:
            budget = validate_budget(budget, min_budget=0.1)
        except (click.UsageError, click.Abort) as e:
            if isinstance(e, click.Abort):
                click.echo("Cancelled")
                return
            click.echo(f"Error: {e}", err=True)
            return

    if not files and not learn:
        click.echo("Error: No files specified. Use --files to add documents or --learn for autonomous learning.")
        click.echo("Example: deepr expert make 'My Expert' -f docs/*.md")
        click.echo("Or: deepr expert make 'My Expert' --learn --budget 10")
        return

    from deepr.cli.commands.semantic.expert_make_profile_setup import confirm_provider_profile_setup

    if not confirm_provider_profile_setup(
        provider=provider, files=files, yes=yes, confirm_metered_profile=confirm_metered_profile
    ):
        return
    click.echo(f"Creating expert: {name}...")

    async def create_expert():
        from datetime import datetime

        from deepr.config import load_config
        from deepr.experts.profile import ExpertProfile, ExpertStore, get_expert_system_message
        from deepr.providers import create_provider

        config = load_config()

        # Get provider-specific API key
        if provider == "gemini":
            api_key = config.get("gemini_api_key")
        elif provider == "azure":
            api_key = config.get("azure_api_key")
        else:
            api_key = config.get("api_key")

        provider_instance = create_provider(provider, api_key=api_key)

        # Upload files and create vector store
        file_ids = []

        if files:
            for file_path in files:
                file_id = await provider_instance.upload_document(file_path)
                file_ids.append(file_id)

        # Create vector store (empty if using --learn)
        vector_store = await provider_instance.create_vector_store(
            name=f"expert-{name.lower().replace(' ', '-')}", file_ids=file_ids
        )

        # Wait for indexing only if there are files
        if files:
            success = await provider_instance.wait_for_vector_store(vector_store.id, timeout=900)
            if not success:
                click.echo("Error: Indexing timed out")
                return None

        # Create expert profile with programmatic system message
        # Set initial knowledge cutoff to now (will be updated when learning is added)
        now = datetime.now(UTC)

        profile = ExpertProfile(
            name=name,
            vector_store_id=vector_store.id,
            description=description,
            domain=description,
            source_files=[str(f) for f in files],
            total_documents=len(files),
            knowledge_cutoff_date=now,  # Initial docs uploaded now
            last_knowledge_refresh=now,
            system_message=get_expert_system_message(
                knowledge_cutoff_date=now,
                domain_velocity="medium",  # Default, can be customized later
            ),
            provider=provider,
        )

        store = ExpertStore()
        store.save(profile)

        return profile

    import os

    profile = asyncio.run(create_expert())

    if not profile:
        return

    # Check if we should generate autonomous learning curriculum
    if learn:
        # Calculate topics and budget based on provided options
        has_topic_counts = any([docs is not None, quick is not None, deep is not None])

        if has_topic_counts:
            # Mode 2 or 3: User specified topic counts
            docs_count = docs or 0
            quick_count = quick or 0
            deep_count = deep or 0

            if docs_count < 0 or quick_count < 0 or deep_count < 0:
                click.echo("Error: Topic counts must be non-negative")
                return

            total_topics = docs_count + quick_count + deep_count

            if total_topics == 0:
                click.echo("Error: Must specify at least one topic (--docs, --quick, or --deep)")
                click.echo("Example: deepr expert make 'Expert' -f test.md --learn --docs 1")
                return

            # Calculate budget from topic counts using actual config values
            from deepr.config import AppConfig

            temp_config = AppConfig.from_env()
            expert_config = temp_config.expert

            # docs and quick are both FOCUS mode (current cheapest capable model)
            # deep is CAMPAIGN mode (o4-mini-deep-research / Gemini deep research: ~$2.50)
            calculated_budget = (
                (docs_count * expert_config.quick_research_cost)
                + (quick_count * expert_config.quick_research_cost)
                + (deep_count * expert_config.deep_research_cost)
            )

            if budget is not None:
                # Mode 3: Validate calculated budget against provided budget
                if calculated_budget > budget:
                    click.echo(
                        f"Error: Calculated budget (${calculated_budget:.2f}) exceeds provided budget (${budget:.2f})"
                    )
                    click.echo("\nTopic breakdown:")
                    click.echo(
                        f"  {docs_count} docs × ${expert_config.quick_research_cost:.3f} = ${docs_count * expert_config.quick_research_cost:.2f}"
                    )
                    click.echo(
                        f"  {quick_count} quick × ${expert_config.quick_research_cost:.3f} = ${quick_count * expert_config.quick_research_cost:.2f}"
                    )
                    click.echo(
                        f"  {deep_count} deep × ${expert_config.deep_research_cost:.2f} = ${deep_count * expert_config.deep_research_cost:.2f}"
                    )
                    click.echo(f"  Total: ${calculated_budget:.2f}")
                    return
                # Use provided budget (may be higher than calculated)
                budget_to_use = budget
            else:
                # Mode 2: Use calculated budget
                budget_to_use = calculated_budget

            # Override topics parameter with calculated total
            topics_to_use = total_topics

        else:
            # Mode 1: Budget only, auto-calculate topic mix
            if not budget:
                click.echo("Error: Either --budget or topic counts (--docs/--quick/--deep) required")
                click.echo("\nExamples:")
                click.echo("  deepr expert make 'Expert' -f docs/*.md --learn --budget 10")
                click.echo("  deepr expert make 'Expert' -f docs/*.md --learn --docs 2 --quick 3 --deep 1")
                return

            if budget <= 0:
                click.echo("Error: Budget must be positive")
                return

            budget_to_use = budget
            # Use default of 15 topics if not specified
            topics_to_use = topics if topics is not None else 15

            # Will be auto-calculated by curriculum generator
            docs_count = None
            quick_count = None
            deep_count = None

        click.echo(f"Generating curriculum ({topics_to_use} topics, ~${budget_to_use:.2f})...")

        # Generate curriculum
        async def generate_and_execute_curriculum():
            from deepr.config import AppConfig
            from deepr.experts.curriculum import CurriculumGenerator
            from deepr.experts.learner import AutonomousLearner

            config = AppConfig.from_env()

            click.echo("Generating curriculum...")

            generator = CurriculumGenerator(config)

            try:
                curriculum = await generator.generate_curriculum(
                    expert_name=name,
                    domain=description or name,
                    initial_documents=[os.path.basename(f) for f in files] if files else [],
                    target_topics=topics_to_use,
                    budget_limit=budget_to_use,
                    docs_count=docs_count,
                    quick_count=quick_count,
                    deep_count=deep_count,
                    enable_discovery=not no_discovery,  # Skip discovery if --no-discovery flag is set
                )

                # Display curriculum summary
                if not curriculum or not curriculum.topics:
                    print_error("Curriculum generation failed - no topics created")
                    return {"error": "No topics generated"}

                print_header(f"Curriculum: {len(curriculum.topics)} topics")

                for i, topic in enumerate(curriculum.topics, 1):
                    console.print(f"{i}. [bold]{topic.title}[/bold]")
                    console.print(f"   [dim]Mode:[/dim] {topic.research_mode} | [dim]Type:[/dim] {topic.research_type}")
                    console.print(
                        f"   [dim]Cost:[/dim] ${topic.estimated_cost:.4f} | [dim]Time:[/dim] ~{topic.estimated_minutes}min"
                    )
                    if topic.sources:
                        console.print(f"   [dim]Sources:[/dim] {len(topic.sources)}")
                    console.print()

                console.print(
                    f"[dim]Total:[/dim] ${curriculum.total_estimated_cost:.2f}, ~{curriculum.total_estimated_minutes}min\n"
                )
                console.print("Starting execution...")

                # Execute curriculum
                learner = AutonomousLearner(config)

                progress = await learner.execute_curriculum(
                    expert=profile, curriculum=curriculum, budget_limit=budget_to_use, dry_run=False
                )

                return progress

            except Exception as e:
                # Return the error so we can handle it with graceful degradation
                return {"error": e}

        result = asyncio.run(generate_and_execute_curriculum())

        # Check if curriculum generation failed
        if result and isinstance(result, dict) and "error" in result:
            error = result["error"]
            click.echo(f"\nError: {error!s}")
            click.echo("Expert created but learning failed. Try again later.")
            return

        progress = result

        if progress:
            click.echo(
                f"\nComplete: {len(progress.completed_topics)}/{len(progress.completed_topics) + len(progress.failed_topics)} topics, ${progress.total_cost:.2f}, {(progress.completed_at - progress.started_at).total_seconds() / 60:.0f}min"
            )

    click.echo(f'\nUsage: deepr chat expert "{profile.name}"')


@expert.command(name="plan")
@click.argument("domain")
@click.option("--budget", type=float, default=None, help="Budget limit for the plan")
@click.option("--topics", type=int, default=15, help="Total number of topics")
@click.option("--no-discovery", is_flag=True, default=False, help="Skip source discovery phase (faster, cheaper)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--csv", "output_csv", is_flag=True, help="Output as CSV")
@click.option("--quiet", "-q", is_flag=True, help="Output prompts only, one per line")
def plan_curriculum(
    domain: str,
    budget: float | None,
    topics: int,
    no_discovery: bool,
    output_json: bool,
    output_csv: bool,
    quiet: bool,
):
    """Generate a research curriculum for any topic - without creating an expert.

    Shows what deepr would research, how much it would cost, and the prompts
    it would use. Great for previewing before committing to --learn.

    EXAMPLES:
      # Pretty table output
      deepr expert plan "Python 3.13 migration"

      # JSON for scripting
      deepr expert plan "Cloud Architecture" --json

      # CSV for spreadsheets
      deepr expert plan "Kubernetes security" --csv

      # Just the prompts, one per line
      deepr expert plan "FastAPI" -q

      # Budget-constrained plan
      deepr expert plan "Azure AI" --budget 10

      # Skip source discovery (faster, cheaper)
      deepr expert plan "React hooks" --no-discovery
    """
    import json as json_mod

    async def generate():
        from deepr.config import AppConfig
        from deepr.experts.curriculum import CurriculumGenerator

        config = AppConfig.from_env()
        generator = CurriculumGenerator(config)

        return await generator.generate_curriculum(
            expert_name=domain,
            domain=domain,
            initial_documents=[],
            target_topics=topics,
            budget_limit=budget,
            enable_discovery=not no_discovery,
        )

    # Generate curriculum
    if not quiet and not output_json and not output_csv:
        console.print(f"[dim]Generating research plan for:[/dim] [bold]{domain}[/bold]")
        if budget:
            console.print(f"[dim]Budget:[/dim] ${budget:.2f}")
        console.print()

    try:
        curriculum = asyncio.run(generate())
    except Exception as e:
        print_error(f"Failed to generate curriculum: {e}")
        return

    if not curriculum or not curriculum.topics:
        print_error("No topics generated")
        return

    # --- JSON output ---
    if output_json:
        click.echo(json_mod.dumps(curriculum.to_dict(), indent=2))
        return

    # --- CSV output ---
    if output_csv:
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["title", "type", "mode", "prompt", "cost", "priority", "dependencies"])
        for t in curriculum.topics:
            writer.writerow(
                [
                    t.title,
                    t.research_type,
                    t.research_mode,
                    t.research_prompt,
                    f"{t.estimated_cost:.4f}",
                    t.priority,
                    ";".join(t.dependencies) if t.dependencies else "",
                ]
            )
        click.echo(buf.getvalue().rstrip())
        return

    # --- Quiet output (prompts only) ---
    if quiet:
        for t in curriculum.topics:
            click.echo(t.research_prompt)
        return

    # --- Default: Rich table ---
    print_header(f"Research Plan: {domain}")

    # Group topics by research_type
    groups: dict[str, list] = {}
    for t in curriculum.topics:
        groups.setdefault(t.research_type, []).append(t)

    topic_num = 0
    for group_name, group_topics in groups.items():
        group_cost = sum(t.estimated_cost for t in group_topics)
        console.print(
            f"\n[bold cyan]{group_name.replace('-', ' ').title()}[/bold cyan]  ({len(group_topics)} topics, ~${group_cost:.2f})"
        )

        for t in group_topics:
            topic_num += 1
            prompt_preview = t.research_prompt[:60] + "..." if len(t.research_prompt) > 60 else t.research_prompt
            console.print(
                f"  {topic_num:>2}. [bold]{t.title:<40}[/bold]  ${t.estimated_cost:<8.3f}[dim]{prompt_preview}[/dim]"
            )

    # Summary footer
    total_hours = curriculum.total_estimated_minutes / 60
    console.print(
        f"\n[bold]Total:[/bold] {len(curriculum.topics)} topics "
        f"· ~${curriculum.total_estimated_cost:.2f} "
        f"· ~{total_hours:.1f} hours"
    )
    console.print("\n[dim]To create an expert with this curriculum:[/dim]")
    console.print(f'  deepr expert make "{domain}" --learn --budget {curriculum.total_estimated_cost:.2f}')


@expert.command(name="list")
def list_experts():
    """List all available experts.

    Shows expert names, descriptions, document counts, conversation history,
    creation dates, and knowledge freshness status.

    USAGE:
      deepr expert list
      deepr expert --list
      deepr expert -l
    """
    from deepr.cli.colors import console, print_header
    from deepr.experts.profile import ExpertStore

    print_header("Domain Experts")

    store = ExpertStore()
    experts = store.list_all()

    if not experts:
        console.print("No experts found.")
        console.print("\nCreate one with:")
        console.print('  deepr expert make "Expert Name" -f documents/*.md')
        return

    console.print(f"Found {len(experts)} expert(s):\n")

    for expert in experts:
        console.print(f"  [bold]Name:[/bold] {expert.name}")
        if expert.description:
            console.print(f"    Description: [dim]{expert.description}[/dim]")
        console.print(f"    Documents: {expert.total_documents}")
        console.print(f"    Conversations: {expert.conversations}")
        if expert.research_triggered > 0:
            console.print(
                f"    Research: {expert.research_triggered} jobs [yellow](${expert.total_research_cost:.2f})[/yellow]"
            )

        # Show temporal information
        created_str = expert.created_at.strftime("%Y-%m-%d")
        updated_str = expert.updated_at.strftime("%Y-%m-%d")

        if created_str == updated_str:
            console.print(f"    Created: {created_str}")
        else:
            console.print(f"    Created: {created_str}, Updated: {updated_str}")

        # Show knowledge freshness status
        if expert.knowledge_cutoff_date:
            freshness = expert.get_freshness_status()
            age_days = freshness.get("age_days", 0)
            status = freshness.get("status", "unknown")
            # Color code the status
            if status == "fresh":
                status_color = "green"
            elif status == "recent":
                status_color = "yellow"
            else:
                status_color = "red"
            console.print(f"    Knowledge: {age_days} days old [{status_color}]{status}[/{status_color}]")

        console.print()

    console.print("Usage:")
    console.print('  deepr chat expert "<name>"')


@expert.command(name="info")
@click.argument("name")
def expert_info(name: str):
    """Show detailed information about an expert."""
    import os

    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        click.echo(f"Error: Expert not found: {name}")
        click.echo("\nList available experts:")
        click.echo("  deepr expert list")
        return

    from deepr.cli.colors import console, print_header, print_key_value

    print_header(f"Expert: {profile.name}")

    print_key_value("Description", profile.description or "N/A")
    print_key_value("Provider", profile.provider)
    print_key_value("Model", profile.model)

    console.print()
    console.print("[bold cyan]Knowledge Base[/bold cyan]")
    print_key_value("Vector Store ID", profile.vector_store_id, indent=1)
    print_key_value("Documents", str(profile.total_documents), indent=1)
    print_key_value("Source Files", str(len(profile.source_files)), indent=1)

    if profile.source_files:
        console.print()
        console.print("  [dim]Files:[/dim]")
        for f in profile.source_files[:10]:
            print_list_item(os.path.basename(f), indent=2)
        if len(profile.source_files) > 10:
            console.print(f"    [dim]... and {len(profile.source_files) - 10} more[/dim]")

    console.print()
    console.print("[bold cyan]Usage Stats[/bold cyan]")
    print_key_value("Conversations", str(profile.conversations), indent=1)
    print_key_value("Research Triggered", str(profile.research_triggered), indent=1)
    print_key_value("Total Research Cost", f"${profile.total_research_cost:.2f}", indent=1)

    if profile.research_jobs:
        print_key_value("Research Jobs", str(len(profile.research_jobs)), indent=1)

    console.print()
    print_key_value("Created", profile.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    print_key_value("Updated", profile.updated_at.strftime("%Y-%m-%d %H:%M:%S"))


@expert.command(name="validate")
@click.argument("name")
@click.argument("claim", required=False)
@click.option(
    "--from-file",
    "-f",
    "from_file",
    type=click.Path(exists=True, dir_okay=False),
    help="Read the claim from a file (use '-' for stdin)",
)
@click.option(
    "--model",
    default=None,
    help="Override the validation model (default: gpt-5-mini, cheap+fast)",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit a structured JSON verdict for machine consumers",
)
@click.option(
    "--max-evidence",
    type=int,
    default=8,
    show_default=True,
    help="Maximum expert beliefs to include as evidence in the assessment",
)
def validate_claim(
    name: str,
    claim: str | None,
    from_file: str | None,
    model: str | None,
    json_output: bool,
    max_evidence: int,
):
    """Validate a claim against an expert's knowledge.

    Returns PASS / WARN / FAIL with citations, confidence, and reasoning.
    Pure read-side: does not modify the expert. Useful as a guardrail for
    downstream agents that need domain validation before acting.

    EXAMPLES:
      # Inline claim
      deepr expert validate "AI Strategy Expert" "GPT-5 is more capable than GPT-4"

      # Claim from file
      deepr expert validate "Security Expert" --from-file claim.txt

      # Claim from stdin (for piping)
      echo "Rust is memory-safe by default" | deepr expert validate "Languages" -f -

      # JSON output for agent consumers
      deepr expert validate "AI Strategy Expert" "..." --json
    """
    import json as _json
    import sys

    from deepr.experts.profile import ExpertStore
    from deepr.services.expert_validator import (
        DEFAULT_VALIDATION_MODEL,
        ExpertValidator,
        ExpertValidatorError,
    )

    # Resolve the claim text from inline arg, file, or stdin.
    if from_file == "-":
        claim_text = sys.stdin.read()
    elif from_file:
        with open(from_file, encoding="utf-8") as f:
            claim_text = f.read()
    elif claim:
        claim_text = claim
    else:
        print_error("Provide a claim inline or via --from-file (use '-' for stdin)")
        sys.exit(2)

    claim_text = (claim_text or "").strip()
    if not claim_text:
        print_error("Claim is empty after reading")
        sys.exit(2)

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    validator = ExpertValidator(
        model=model or DEFAULT_VALIDATION_MODEL,
        max_evidence=max_evidence,
    )

    try:
        result = asyncio.run(validator.validate(profile, claim_text))
    except ExpertValidatorError as e:
        print_error(str(e))
        sys.exit(2)
    except Exception as e:
        # Surface provider-side failures (rate limit, transient outage) as
        # a clean error rather than a stack trace.
        print_error(f"Validation failed: {e}")
        sys.exit(1)

    if json_output:
        click.echo(_json.dumps(result.to_dict(), indent=2))
        return

    # Human-readable output. Use color to make the verdict glance-able.
    verdict_color = {"pass": "green", "warn": "yellow", "fail": "red"}[result.verdict]
    print_header(f"Validation: {profile.name}")
    console.print(f"Claim: [white]{result.claim}[/white]")
    console.print(
        f"Verdict: [bold {verdict_color}]{result.verdict.upper()}[/bold {verdict_color}] "
        f"[dim](confidence {result.confidence:.0%}, model {result.model})[/dim]"
    )
    console.print()
    console.print("[bold]Reasoning[/bold]")
    console.print(f"  {result.reasoning}")

    if result.supporting:
        console.print()
        print_section_header("Supporting beliefs")
        for c in result.supporting:
            print_list_item(f"{c.statement}  [dim](conf {c.confidence:.2f})[/dim]")

    if result.contradicting:
        console.print()
        print_section_header("Contradicting beliefs")
        for c in result.contradicting:
            print_list_item(f"{c.statement}  [dim](conf {c.confidence:.2f})[/dim]")

    if result.caveats:
        console.print()
        print_section_header("Caveats")
        for cv in result.caveats:
            print_list_item(cv)

    if result.verdict == "fail":
        print_warning("Downstream agents should not act on the claim without further review.")
    elif result.verdict == "warn":
        print_warning("Expert evidence is thin or partial; treat with caution.")
    else:
        print_success("Claim is consistent with expert knowledge.")


@expert.command(name="health-check")
@click.argument("name")
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the full structured health report as JSON",
)
@click.option(
    "--archive-stale",
    "archive_stale",
    is_flag=True,
    help="Archive the eligible stale beliefs (reversible; snapshots kept in the event log)",
)
@click.option(
    "--scheduled",
    is_flag=True,
    help="Emit scheduler action state and avoid prompts or metered actions",
)
@click.option(
    "--jitter",
    type=click.FloatRange(min=0.0),
    default=0.0,
    show_default=True,
    help="With --archive-stale --scheduled --yes: maximum startup jitter in seconds before archival",
)
@click.option("--yes", "-y", is_flag=True, help="With --archive-stale: skip confirmation")
def health_check(name: str, json_output: bool, archive_stale: bool, scheduled: bool, jitter: float, yes: bool):
    """Audit an expert's knowledge state. Read-only, costs nothing.

    Runs a set of free, read-side checks - knowledge freshness, belief
    contradictions (heuristic), claims missing source provenance, beliefs
    decayed below the confidence threshold, lifecycle archive candidates, the
    open-gap backlog, and ingested documents that were never synthesized - and
    prints findings plus a recommended-action menu. Each recommended action
    carries its CLI command, an estimated cost, and the approval tier that
    would gate it. The audit only proposes; running an action is a separate,
    opt-in step.

    With --archive-stale, the archive-candidates action executes: beliefs that
    are decayed below the floor, long-unevidenced, unused, and not contested
    are archived ($0, no LLM). Every archival is event-logged with a full
    snapshot, so it is reversible belief-by-belief.

    EXAMPLES:
      deepr expert health-check "AI Strategy Expert"
      deepr expert health-check "AI Strategy Expert" --json
      deepr expert health-check "AI Strategy Expert" --archive-stale
      deepr expert health-check "AI Strategy Expert" --scheduled --json
    """
    import json as _json
    import sys

    from deepr.cli.commands.semantic.expert_health_loop import record_completed_health_check
    from deepr.experts.health_check import ExpertHealthChecker
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    if archive_stale:
        from deepr.cli.commands.semantic.expert_health_archive import (
            archive_stale_with_scheduled_guard,
            canonical_profile_name,
        )

        archive_stale_with_scheduled_guard(
            name,
            profile_name=canonical_profile_name(profile, name),
            yes=yes,
            json_output=json_output,
            scheduled=scheduled,
            jitter=jitter,
        )
        return

    report = ExpertHealthChecker(profile).run()

    if json_output:
        if scheduled:
            from deepr.cli.commands.semantic.expert_health_schedule import scheduled_health_payload

            click.echo(_json.dumps(scheduled_health_payload(report), indent=2))
            return
        loop_run = record_completed_health_check(report)
        payload = report.to_dict()
        payload["loop_run"] = loop_run.to_dict()
        click.echo(_json.dumps(payload, indent=2))
        return

    status_color = {"healthy": "green", "needs_attention": "yellow", "critical": "red"}.get(report.status, "white")
    print_header(f"Health Check: {report.expert_name}")
    console.print(
        f"Overall: [bold {status_color}]{report.status.replace('_', ' ').upper()}[/bold {status_color}]"
        f"  [dim]{report.domain}[/dim]"
    )

    severity_marker = {
        "critical": "[red]FAIL[/red]",
        "warning": "[yellow]WARN[/yellow]",
        "info": "[cyan]INFO[/cyan]",
        "ok": "[green] OK [/green]",
    }
    console.print()
    print_section_header("Findings")
    for f in report.findings:
        marker = severity_marker.get(f.severity, f.severity)
        console.print(f"  {marker} [bold]{f.category}[/bold]: {f.summary}")

    if report.actions:
        console.print()
        print_section_header("Recommended actions")
        for a in report.actions:
            cost = "free" if a.estimated_cost <= 0 else f"~${a.estimated_cost:.2f}"
            console.print(f"  - {a.description} [dim]({cost}, approval: {a.approval_tier})[/dim]")
            console.print(f"    [white]{a.command}[/white]")
    else:
        console.print()
        print_success("No corrective actions recommended.")

    if scheduled:
        from deepr.cli.commands.semantic.expert_health_schedule import (
            print_scheduled_health_action_plan,
            scheduled_health_action_plan,
        )

        console.print()
        print_scheduled_health_action_plan(scheduled_health_action_plan(report))

    if report.status == "critical":
        print_warning("This expert needs attention before it should be relied on.")
    record_completed_health_check(report)


@expert.command(name="what-changed")
@click.argument("name")
@click.option("--since", default="7d", help="ISO 8601 timestamp, or relative shorthand like 7d / 24h / 30m")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def what_changed_cmd(name: str, since: str, json_output: bool):
    """Show how NAME's perspective changed since a point in time.

    Read-only and cost-$0. Buckets belief changes after --since into
    added / revised / contested / archived, each with its reason and a
    current snapshot. This is the re-sync query: catch up with an expert
    you consulted before instead of re-reading everything.

    EXAMPLES:
      deepr expert what-changed "AI Strategy Expert" --since 7d
      deepr expert what-changed "AI Strategy Expert" --since 2026-06-01
    """
    import json as _json
    import re
    import sys
    from datetime import UTC, datetime, timedelta

    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.perspective import what_changed as _what_changed
    from deepr.experts.profile import ExpertStore

    if not ExpertStore().load(name):
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    rel = re.fullmatch(r"(\d+)([dhm])", since.strip().lower())
    if rel:
        amount, unit = int(rel.group(1)), rel.group(2)
        delta = {"d": timedelta(days=amount), "h": timedelta(hours=amount), "m": timedelta(minutes=amount)}[unit]
        since_dt = datetime.now(UTC) - delta
    else:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            print_error(f"--since is neither ISO 8601 nor relative (7d/24h/30m): {since}")
            sys.exit(2)

    result = _what_changed(BeliefStore(name), since_dt, expert_name=name)

    if json_output:
        click.echo(_json.dumps(result.to_dict(), indent=2))
        return

    print_header(f"Perspective delta: {name}")
    console.print(f"Since {result.since.isoformat()}  -  {result.total_changes} change(s)")
    if result.window_truncated:
        print_warning("Change history window truncated (last 100 records); earlier changes not shown.")

    for title, entries in (
        ("Added", result.added),
        ("Revised", result.revised),
        ("Contested", result.contested),
        ("Archived", result.archived),
    ):
        if not entries:
            continue
        console.print()
        print_section_header(f"{title} ({len(entries)})")
        for e in entries:
            console.print(f"  - {e['claim']}  [dim](conf {e['confidence']:.2f})[/dim]")
            if e.get("reason"):
                console.print(f"    [dim]{e['reason']}[/dim]")

    if result.total_changes == 0:
        console.print("[dim]No changes in this window.[/dim]")


@expert.command(name="why")
@click.argument("name")
@click.argument("belief_ref")
@click.option("--depth", type=int, default=2, show_default=True, help="Max hops along support chains")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def why_cmd(name: str, belief_ref: str, depth: int, json_output: bool):
    """Explain why NAME believes something - evidence, history, and chains.

    Read-only and cost-$0. BELIEF_REF is a belief id or claim text (fuzzy
    matched). Shows the evidence roots (provenance), the confidence
    trajectory from the append-only event log, the supporting/derived-from
    chains walked over the typed belief graph, and any open contradictions.
    This is the introspection query - the third temporal query after
    what-changed and contested.

    EXAMPLES:
      deepr expert why "MCP Interop Expert" "dynamic tool discovery"
      deepr expert why "AI Strategy Expert" belief-a1b2c3 --depth 3 --json
    """
    import json as _json
    import sys

    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.perspective import explain_belief as _explain_belief
    from deepr.experts.profile import ExpertStore

    if not ExpertStore().load(name):
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    result = _explain_belief(BeliefStore(name), belief_ref, expert_name=name, depth=depth)
    if result is None:
        print_error(f"No belief matches: {belief_ref}")
        console.print("List beliefs via the expert profile or what-changed; ids look like belief-<hex>.")
        sys.exit(2)

    if json_output:
        click.echo(_json.dumps(result.to_dict(), indent=2))
        return

    b = result.belief
    print_header(f"Why: {name}")
    console.print(f"  {b['claim']}")
    console.print(f"  [dim]confidence {b['confidence']:.2f}  -  {b['belief_id']}  -  source: {b['source_type']}[/dim]")

    if result.evidence_roots:
        console.print()
        print_section_header(f"Evidence ({len(result.evidence_roots)})")
        for ref in result.evidence_roots:
            console.print(f"  - {ref}")

    if result.trajectory:
        console.print()
        print_section_header(f"History ({len(result.trajectory)})")
        for t in result.trajectory:
            line = f"  {t['timestamp'][:16]}  {t['change_type']:<9} conf {t['confidence']:.2f}"
            if t.get("reason"):
                line += f"  [dim]{t['reason'][:60]}[/dim]"
            console.print(line)

    for title, entries in (("Supported by", result.supports), ("Derived from", result.derived_from)):
        if not entries:
            continue
        console.print()
        print_section_header(f"{title} ({len(entries)})")
        for e in entries:
            console.print(f"  - {e['claim']}  [dim](conf {e['confidence']}, {e['hops']} hop(s))[/dim]")
            if e.get("provenance"):
                console.print(f"    [dim]via {', '.join(e['provenance'][:3])}[/dim]")

    if result.contradicts:
        console.print()
        print_section_header(f"Contradicted by ({len(result.contradicts)})")
        for c in result.contradicts:
            console.print(f"  - {c['claim']}  [dim](conf {c['confidence']}, {c['status']})[/dim]")
        console.print(f"  [dim]Adjudicate: deepr expert resolve-conflicts '{name}'[/dim]")

    if not (result.evidence_roots or result.trajectory or result.supports or result.contradicts):
        console.print("[dim]No recorded evidence, history, or graph context for this belief.[/dim]")


@expert.command(name="contested")
@click.argument("name")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def contested_cmd(name: str, json_output: bool):
    """Show NAME's open contradictions - both sides, confidence, provenance.

    Read-only and cost-$0. Surfaces live conflicts (recorded by absorb-time
    flagging and belief integration) instead of a smoothed narrative.
    Resolve them with: deepr expert resolve-conflicts NAME

    EXAMPLE:
      deepr expert contested "AI Strategy Expert"
    """
    import json as _json
    import sys

    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.perspective import contested as _contested
    from deepr.experts.profile import ExpertStore

    if not ExpertStore().load(name):
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    result = _contested(BeliefStore(name), expert_name=name)

    if json_output:
        click.echo(_json.dumps(result, indent=2))
        return

    print_header(f"Contested beliefs: {name}")
    console.print(f"{result['contested_count']} pair(s), {result['open_count']} open")
    for pair in result["pairs"]:
        console.print()
        marker = "[yellow]open[/yellow]" if pair["status"] == "open" else "[dim]dangling[/dim]"
        console.print(f"  [{marker}]")
        console.print(f"  A: {pair['a']['claim']}  [dim](conf {pair['a'].get('confidence', 0):.2f})[/dim]")
        b_claim = pair["b"].get("claim") or f"<{pair['b'].get('note', 'missing')}>"
        b_conf = pair["b"].get("confidence")
        conf_str = f"  [dim](conf {b_conf:.2f})[/dim]" if isinstance(b_conf, (int, float)) else ""
        console.print(f"  B: {b_claim}{conf_str}")

    if result["contested_count"] == 0:
        console.print("[dim]No contested beliefs.[/dim]")
    else:
        console.print(f"\nAdjudicate with: deepr expert resolve-conflicts '{name}'")


@expert.command(name="digest")
@click.argument("name")
@click.option("--print", "print_only", is_flag=True, help="Print to stdout instead of writing the file")
@click.option("--force", is_flag=True, help="Overwrite even if the existing file looks hand-edited")
def digest_cmd(name: str, print_only: bool, force: bool):
    """Compile NAME's belief store into a browsable digest (derived view).

    Read-only over the store, $0, no LLM call - synthesis happens at
    compile time over structured truth. The digest is always regenerable
    and never authoritative: the belief store stays canonical. Open
    contradictions are surfaced, not smoothed over. Byte-stable for an
    unchanged store (the "as of" stamp comes from the latest belief
    event, not the clock).

    Writes <knowledge dir>/digest.md by default; refuses to overwrite a
    file that lost its derived-view marker (it may have been hand-edited,
    which the regeneration invariant exists to prevent) unless --force.

    EXAMPLES:
      deepr expert digest "MCP Interop Expert"
      deepr expert digest "AI Strategy Expert" --print
    """
    import sys

    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.digest import DIGEST_MARKER, build_digest
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    if not store.load(name):
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    content = build_digest(BeliefStore(name), expert_name=name)

    if print_only:
        click.echo(content)
        return

    out_path = store.get_knowledge_dir(name) / "digest.md"
    if out_path.exists() and DIGEST_MARKER not in out_path.read_text(encoding="utf-8", errors="replace"):
        if not force:
            print_error(
                f"{out_path} exists without the derived-view marker - it may have been hand-edited. "
                "The digest is a regenerable view, never authoritative; use --force to overwrite."
            )
            sys.exit(2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print_success(f"Digest written: {out_path}")
    console.print("[dim]Derived view - regenerate any time; the belief store stays canonical.[/dim]")


@expert.command(name="subscribe")
@click.argument("name")
@click.argument("topic")
@click.option("--query", "-q", default="", help="Extra focus for the freshness prompt")
@click.option("--every", "cadence_days", type=float, default=7.0, show_default=True, help="Refresh cadence in days")
@click.option("--budget", "-b", type=float, default=0.50, show_default=True, help="Per-sync budget for this topic")
def subscribe_cmd(name: str, topic: str, query: str, cadence_days: float, budget: float):
    """Subscribe NAME to a topic so `deepr expert sync` keeps it current.

    EXAMPLES:
      deepr expert subscribe "MCP Interop Expert" "MCP specification changes"
      deepr expert subscribe "AI Policy Expert" "EU AI Act enforcement" --every 3 --budget 1
    """
    import sys

    from deepr.experts.profile import ExpertStore
    from deepr.experts.sync import Subscription, SubscriptionStore

    if not ExpertStore().load(name):
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    store = SubscriptionStore(name)
    try:
        store.add(Subscription(topic=topic, query=query, cadence_days=cadence_days, budget=budget))
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    print_success(f"Subscribed '{name}' to: {topic} (every {cadence_days:g}d, ${budget:.2f}/sync)")
    console.print(f"Run when due: deepr expert sync '{name}'")


@expert.command(name="subscriptions")
@click.argument("name")
@click.option("--remove", "remove_topic", default=None, help="Unsubscribe from a topic")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def subscriptions_cmd(name: str, remove_topic: str | None, json_output: bool):
    """List (or remove) NAME's topic subscriptions."""
    import json as _json
    import sys
    from datetime import UTC, datetime

    from deepr.experts.profile import ExpertStore
    from deepr.experts.sync import SubscriptionStore

    if not ExpertStore().load(name):
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    store = SubscriptionStore(name)

    if remove_topic:
        if store.remove(remove_topic):
            print_success(f"Unsubscribed from: {remove_topic}")
        else:
            print_error(f"No subscription found for: {remove_topic}")
            sys.exit(2)
        return

    if json_output:
        click.echo(_json.dumps({"subscriptions": [s.to_dict() for s in store.subscriptions]}, indent=2))
        return

    print_header(f"Subscriptions: {name}")
    if not store.subscriptions:
        console.print("[dim]No subscriptions. Add one with: deepr expert subscribe[/dim]")
        return
    now = datetime.now(UTC)
    for s in store.subscriptions:
        due = "[yellow]due[/yellow]" if s.is_due(now) else "current"
        last = s.last_synced.strftime("%Y-%m-%d %H:%M") if s.last_synced else "never"
        console.print(
            f"  - {s.topic}  [dim](every {s.cadence_days:g}d, ${s.budget:.2f}/sync, last: {last})[/dim]  {due}"
        )


@expert.command(name="delete")
@click.argument("name")
@click.option("--purge", is_flag=True, help="Hard delete without archiving (irreversible).")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_expert(name: str, purge: bool, yes: bool):
    """Delete an expert. By default its whole directory is archived (compressed
    to a gitignored archive folder) before removal so it can be restored;
    --purge skips the archive and deletes outright."""
    from deepr.cli.commands.semantic.expert_cleanup import archive_expert
    from deepr.experts.paths import canonical_expert_dir
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        return

    action = "Delete" if purge else "Archive and delete"
    if not yes and not click.confirm(f"{action} expert '{profile.name}'?"):
        click.echo("Cancelled")
        return

    if not purge and canonical_expert_dir(name).exists():
        console.print(f"[dim]Archived to {archive_expert(name)}[/dim]")

    if store.delete(name, remove_directory=True):
        print_success(f"Expert {'deleted' if purge else 'archived and deleted'}: {name}")
        vsid = getattr(profile, "vector_store_id", "")
        if vsid and not str(vsid).startswith("local"):
            console.print(f"Knowledge base (vector store) remains; delete with: deepr knowledge delete {vsid}")
    else:
        print_error("Failed to delete expert")


@expert.command(name="learn")
@click.argument("name")
@click.argument("topic", required=False)
@click.option(
    "--files", "-f", multiple=True, type=click.Path(exists=True), help="Files to add to expert's knowledge base"
)
@click.option("--budget", "-b", type=float, default=1.0, help="Budget limit for topic research (default: $1)")
@click.option(
    "--synthesize/--no-synthesize", default=True, help="Re-synthesize consciousness after learning (default: yes)"
)
@click.option("--model", default=None, help="Local Ollama model for topic research + extraction")
@click.option("--plan", "plan", default=None, help="Use a plan-quota CLI backend for topic learning")
@click.option("--plan-model", "plan_model", default=None, help="Model to pass to the plan-quota CLI")
@click.option(
    "--num-results", type=int, default=8, show_default=True, help="Web results to retrieve for topic learning"
)
@click.option("--max-pages", type=int, default=5, show_default=True, help="Top web results to fetch in full")
@click.option("--min-confidence", type=float, default=0.6, show_default=True, help="Drop weaker extracted claims")
@click.option("--dry-run", is_flag=True, help="Preview topic claims; write no beliefs")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def learn_expert(
    name: str,
    topic: str | None,
    files: tuple,
    budget: float,
    synthesize: bool,
    model: str | None,
    plan: str | None,
    plan_model: str | None,
    num_results: int,
    max_pages: int,
    min_confidence: float,
    dry_run: bool,
    yes: bool,
):
    """Add knowledge to an expert on demand.

    Topic learning uses live web retrieval plus verified belief absorption on
    local or explicit plan capacity. Files still use the document-upload path.
    """
    import asyncio
    import os
    from datetime import datetime
    from pathlib import Path

    from deepr.cli.validation import validate_budget
    from deepr.config import AppConfig
    from deepr.experts.profile import ExpertStore
    from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview
    from deepr.providers import create_provider

    if not topic and not files:
        click.echo("Error: Must provide either a topic to research or files to upload.")
        click.echo('  deepr expert learn "Expert Name" "Topic to research"')
        click.echo('  deepr expert learn "Expert Name" --files docs/*.md')
        return

    if dry_run and files:
        click.echo("Error: --dry-run is only supported for topic learning without files.")
        return

    if topic:
        from deepr.cli.commands.semantic.expert_maintenance import run_learn_web_pipeline

        if budget != 1.0 and not dry_run:
            console.print(
                "[dim]Topic learning uses owned/prepaid capacity; --budget is ignored unless files use legacy upload.[/dim]"
            )
        run_learn_web_pipeline(
            name=name,
            topic=topic,
            model=model,
            plan=plan,
            plan_model=plan_model,
            num_results=num_results,
            max_pages=max_pages,
            min_confidence=min_confidence,
            save_path=None,
            dry_run=dry_run,
            yes=yes,
            json_output=False,
            title=f"Learn: {name}",
        )
        if not files:
            return
        topic = None

    if not yes:
        try:
            budget = validate_budget(budget, min_budget=0.1)
        except (click.UsageError, click.Abort) as e:
            if isinstance(e, click.Abort):
                click.echo("Cancelled")
                return
            click.echo(f"Error: {e}", err=True)
            return

    print_header(f"Learn: {name}")

    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        print_error(f"Expert not found: {name}")
        console.print("\nList available experts:")
        console.print("  deepr expert list")
        return

    if topic:
        print_key_value("Topic to research", topic)
        print_key_value("Research budget", f"${budget:.2f}")

    if files:
        print_key_value("Files to upload", str(len(files)))
        for f in files[:5]:
            console.print(f"  [dim]-[/dim] {os.path.basename(f)}")
        if len(files) > 5:
            console.print(f"  [dim]... and {len(files) - 5} more[/dim]")

    print_key_value("Synthesize after learning", "Yes" if synthesize else "No")

    if not yes:
        if not click.confirm("\nProceed with learning?"):
            click.echo("Cancelled")
            return

    async def do_learn():
        from deepr.experts.chat import ExpertChatSession

        config = AppConfig.from_env()
        provider = create_provider("openai", api_key=config.provider.openai_api_key)

        total_cost = 0.0
        documents_added = 0
        research_results = []

        if topic:
            print_section_header("Phase 1: Researching Topic")

            session = ExpertChatSession(profile, budget=budget, agentic=True)

            console.print(f"[dim]Query:[/dim] {topic[:80]}{'...' if len(topic) > 80 else ''}")
            console.print("Researching...")

            try:
                result = await session._standard_research(topic)

                if "error" in result:
                    print_error(f"Research failed: {result['error']}")
                else:
                    cost = result.get("cost", 0.0)
                    total_cost += cost
                    documents_added += 1
                    research_results.append(result)
                    print_success(f"Research complete (${cost:.4f})")

                    answer = result.get("answer", "")
                    if answer:
                        snippet = answer[:200] + "..." if len(answer) > 200 else answer
                        console.print(f"\n[dim]Learned:[/dim]\n{snippet}")

            except Exception as e:
                print_error(f"Research error: {e}")

        if files:
            print_section_header("Phase 2: Uploading Files")

            docs_dir = store.get_documents_dir(name)
            docs_dir.mkdir(parents=True, exist_ok=True)

            uploaded_files = []
            for file_path in files:
                try:
                    src_path = Path(file_path)
                    dst_path = docs_dir / src_path.name

                    import shutil

                    shutil.copy2(src_path, dst_path)
                    uploaded_files.append(dst_path)
                    print_success(f"Copied: {src_path.name}")

                except Exception as e:
                    print_error(f"Failed to copy {file_path}: {e}")

            if uploaded_files:
                click.echo(f"\nUploading {len(uploaded_files)} files to vector store...")

                try:
                    for file_path in uploaded_files:
                        file_id = await provider.upload_document(str(file_path))
                        await provider.add_file_to_vector_store(profile.vector_store_id, file_id)
                        documents_added += 1
                        console.print(f"[success]Indexed: {file_path.name}[/success]")

                    profile.total_documents += len(uploaded_files)
                    profile.source_files.extend([str(f) for f in uploaded_files])
                    profile.updated_at = datetime.now(UTC)
                    store.save(profile)

                except Exception as e:
                    print_error(f"Vector store upload failed: {e}")

        if synthesize and documents_added > 0:
            print_section_header("Phase 3: Re-synthesizing Consciousness")
            console.print("Expert is integrating new knowledge into beliefs...")

            try:
                synthesizer = KnowledgeSynthesizer(provider.client)

                knowledge_dir = store.get_knowledge_dir(name)
                worldview_path = knowledge_dir / "worldview.json"
                existing_worldview = None

                if worldview_path.exists():
                    try:
                        existing_worldview = Worldview.load(worldview_path)
                    except Exception:
                        pass  # Will create new worldview (corrupt or missing is recoverable)

                docs_dir = store.get_documents_dir(name)
                all_docs = list(docs_dir.glob("*.md"))
                docs_to_process = [{"path": str(f)} for f in all_docs[:20]]  # Limit to 20

                synthesis_result = await synthesizer.synthesize_new_knowledge(
                    expert_name=profile.name,
                    domain=profile.domain or profile.description,
                    new_documents=docs_to_process,
                    existing_worldview=existing_worldview,
                )

                if synthesis_result["success"]:
                    new_worldview = synthesis_result["worldview"]
                    new_worldview.save(worldview_path)

                    worldview_md_path = knowledge_dir / "worldview.md"
                    try:
                        worldview_doc = await synthesizer.generate_worldview_document(
                            new_worldview, synthesis_result.get("reflection", "")
                        )
                        worldview_md_path.write_text(worldview_doc, encoding="utf-8")
                    except Exception:
                        pass  # Non-critical: JSON worldview already saved; markdown is optional view

                    print_success("Synthesis complete!")
                    click.echo(f"    Beliefs: {len(new_worldview.beliefs)}")
                    click.echo(f"    Knowledge gaps: {len(new_worldview.knowledge_gaps)}")

                    if synthesis_result.get("beliefs_formed", 0) > 0:
                        click.echo(f"    New beliefs formed: {synthesis_result['beliefs_formed']}")
                else:
                    console.print(f"[warning]Synthesis failed: {synthesis_result.get('error', 'Unknown')}[/warning]")

            except Exception as e:
                console.print(f"[warning]Synthesis error: {e}[/warning]")

        return {"documents_added": documents_added, "total_cost": total_cost, "research_results": len(research_results)}

    result = asyncio.run(do_learn())

    print_header("Learning Complete")
    print_key_value("Documents added", str(result["documents_added"]))
    if result["research_results"] > 0:
        print_key_value("Research queries", str(result["research_results"]))
    print_key_value("Total cost", f"${result['total_cost']:.4f}")

    if synthesize and result["documents_added"] > 0:
        console.print("\nExpert consciousness has been updated.")
    elif result["documents_added"] > 0:
        console.print("\nKnowledge added. Run with --synthesize to update consciousness.")

    console.print(f'\nChat with: deepr chat expert "{name}"')


@expert.command(name="resume")
@click.argument("name")
@click.option(
    "--budget", "-b", type=float, default=None, help="Budget limit for remaining topics (default: use original budget)"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def resume_expert_learning(name: str, budget: float | None, yes: bool):
    """Resume paused autonomous learning for an expert."""
    import asyncio

    from deepr.cli.validation import validate_budget, validate_expert_name
    from deepr.config import AppConfig
    from deepr.experts.curriculum import LearningCurriculum, LearningTopic
    from deepr.experts.learner import AutonomousLearner
    from deepr.experts.profile import ExpertStore

    try:
        name = validate_expert_name(name)
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    print_header(f"Resume Learning: {name}")

    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        print_error(f"Expert not found: {name}")
        console.print("\nList available experts:")
        console.print("  deepr expert list")
        return

    config = AppConfig.from_env()
    learner = AutonomousLearner(config)
    saved_progress = learner.load_learning_progress(name)

    if not saved_progress:
        print_error("No saved progress found for this expert")
        console.print("\nThis expert has no paused learning session to resume.")
        console.print("To start new learning, use:")
        console.print(f'  deepr expert learn "{name}" "topic to research"')
        return

    remaining_topics = saved_progress.get("remaining_topics", [])
    completed_topics = saved_progress.get("completed_topics", [])
    failed_topics = saved_progress.get("failed_topics", [])
    cost_so_far = saved_progress.get("total_cost_so_far", 0.0)
    paused_at = saved_progress.get("paused_at", "unknown")

    print_key_value("Paused at", paused_at)
    print_key_value("Completed topics", str(len(completed_topics)))
    print_key_value("Failed topics", str(len(failed_topics)))
    print_key_value("Remaining topics", str(len(remaining_topics)))
    print_key_value("Cost so far", f"${cost_so_far:.2f}")

    if not remaining_topics:
        print_error("No remaining topics to process")
        console.print("\nClearing saved progress...")
        learner.clear_learning_progress(name)
        console.print("Done. All topics were already processed.")
        return

    # Calculate estimated cost for remaining topics
    estimated_remaining_cost = sum(t.get("estimated_cost", 0.5) for t in remaining_topics)
    print_key_value("Estimated remaining cost", f"${estimated_remaining_cost:.2f}")

    # Determine budget
    if budget is None:
        # Use a reasonable default based on remaining work
        budget = max(estimated_remaining_cost * 1.5, 5.0)  # 50% buffer, min $5
        console.print(f"\n[dim]Using default budget: ${budget:.2f}[/dim]")

    # Validate budget
    if not yes:
        try:
            budget = validate_budget(budget, min_budget=0.1)
        except (click.UsageError, click.Abort) as e:
            if isinstance(e, click.Abort):
                click.echo("Cancelled")
                return
            click.echo(f"Error: {e}", err=True)
            return

    # Show remaining topics
    console.print("\nRemaining topics:")
    for i, topic in enumerate(remaining_topics[:5], 1):
        console.print(f"  {i}. {topic.get('title', 'Unknown')}")
    if len(remaining_topics) > 5:
        console.print(f"  ... and {len(remaining_topics) - 5} more")

    if not yes:
        if not click.confirm(f"\nResume learning with ${budget:.2f} budget?"):
            click.echo("Cancelled")
            return

    async def do_resume():
        # Rebuild curriculum from remaining topics
        topics = []
        for t in remaining_topics:
            topic = LearningTopic(
                title=t.get("title", "Unknown"),
                description=t.get("description", ""),
                research_prompt=t.get("research_prompt", ""),
                research_mode=t.get("research_mode", "focus"),
                research_type=t.get("research_type", "general"),
                estimated_cost=t.get("estimated_cost", 0.5),
                estimated_minutes=t.get("estimated_minutes", 5),
                priority=t.get("priority", 3),
            )
            topics.append(topic)

        curriculum = LearningCurriculum(
            expert_name=name,
            domain=profile.domain or profile.description or name,
            topics=topics,
            total_estimated_cost=estimated_remaining_cost,
            total_estimated_minutes=sum(t.get("estimated_minutes", 5) for t in remaining_topics),
            generated_at=datetime.now(UTC),
        )

        # Execute with resume=True
        progress = await learner.execute_curriculum(
            expert=profile, curriculum=curriculum, budget_limit=budget, dry_run=False, resume=True
        )

        return progress

    progress = asyncio.run(do_resume())

    if progress:
        print_header("Resume Complete")
        print_key_value("Completed", f"{len(progress.completed_topics)} topics")
        print_key_value("Failed", f"{len(progress.failed_topics)} topics")
        print_key_value("Total cost", f"${progress.total_cost:.2f}")
        print_key_value("Success rate", f"{progress.success_rate() * 100:.1f}%")

        if progress.is_complete():
            console.print("\nAll topics processed. Learning complete.")
        else:
            console.print("\nSome topics remain. Run again to continue:")
            console.print(f'  deepr expert resume "{name}"')

    console.print(f'\nChat with: deepr chat expert "{name}"')


@expert.command(name="reflect")
@click.argument("name")
@click.argument("report_id")
@click.option("--depth", type=int, default=1, show_default=True, help="0 = skip, 1 = single pass, 2+ = rigorous")
@click.option("--json", "json_output", is_flag=True, help="Emit the structured reflection report as JSON")
@click.option(
    "--execute-followups",
    is_flag=True,
    help="Run the follow-up queries reflection emits (budget-bounded; findings absorb verification-gated)",
)
@click.option("--budget", "-b", type=float, default=1.0, show_default=True, help="Budget ceiling for follow-ups")
@click.option("--scheduled", is_flag=True, help="Wait instead of spending from recurring reflection jobs")
@click.option("--yes", "-y", is_flag=True, help="Skip follow-up confirmation")
def reflect_report(
    name: str,
    report_id: str,
    depth: int,
    json_output: bool,
    execute_followups: bool,
    budget: float,
    scheduled: bool,
    yes: bool,
):
    """Self-evaluate a research report before relying on or absorbing it.

    Scores the report against its question on grounding, completeness,
    calibration, and directness, then returns a verdict (accept / revise /
    re-research) with concrete issues and follow-up queries. Judged in the
    context of NAME's domain. A natural pre-step to `expert absorb`. Costs one
    small evaluation call.

    With --execute-followups the loop closes: the emitted follow-up queries
    actually run (budget-bounded, skip-not-fail) and their findings absorb
    through the verification-gated pipeline - reflection stops being
    advisory exactly when the report needs reinforcement.

    EXAMPLES:
      deepr expert reflect "AI Strategy Expert" <job_id>
      deepr expert reflect "AI Strategy Expert" <job_id> --execute-followups --budget 1 -y
      deepr expert reflect "AI Strategy Expert" <job_id> --execute-followups --scheduled --json
    """
    import json as _json
    import sys

    from deepr.experts.profile import ExpertStore
    from deepr.services.context_index import ContextIndex

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    index = ContextIndex()
    result = index.get_report_by_job_id(report_id)
    report_text = index.get_report_content(report_id, max_chars=100000)
    if not report_text or not result:
        print_error(f"No report found for id: {report_id}")
        click.echo("Find report/job IDs with: deepr search")
        sys.exit(2)

    if scheduled:
        from deepr.cli.commands.semantic.expert_reflect_schedule import dispatch_scheduled_reflection

        dispatch_scheduled_reflection(
            profile,
            name,
            report_id,
            result.prompt,
            report_text,
            depth=depth,
            execute_followups=execute_followups,
            budget=budget,
            json_output=json_output,
        )
        return

    from deepr.cli.commands.semantic.expert_reflection_loop import record_completed_reflection_loop
    from deepr.experts.reflection import ReflectionEngine, ReflectionError

    engine = ReflectionEngine()
    try:
        report = asyncio.run(engine.reflect(result.prompt, report_text, domain=profile.domain or "", depth=depth))
    except ReflectionError as e:
        print_error(str(e))
        sys.exit(2)
    except Exception as e:
        print_error(f"Reflection failed: {e}")
        sys.exit(1)

    if json_output:
        loop_run = record_completed_reflection_loop(
            profile.name,
            report_id,
            report,
            budget=budget,
            execute_followups=execute_followups,
        )
        payload = report.to_dict()
        payload["loop_run"] = loop_run.to_dict()
        click.echo(_json.dumps(payload, indent=2))
        return

    verdict_color = {"accept": "green", "revise": "yellow", "re_research": "red", "skipped": "dim"}.get(
        report.verdict, "white"
    )
    print_header(f"Reflection: {result.prompt[:60]}")
    console.print(
        f"Verdict: [bold {verdict_color}]{report.verdict.upper()}[/bold {verdict_color}] "
        f"[dim](overall {report.overall_score:.0%}, model {report.model})[/dim]"
    )
    if report.dimensions:
        console.print()
        print_section_header("Dimensions")
        for d in report.dimensions:
            console.print(f"  {d.score:.0%}  [bold]{d.name}[/bold]: {d.assessment}")
            for issue in d.issues:
                console.print(f"      [dim]- {issue}[/dim]")
    if report.followups:
        console.print()
        print_section_header("Suggested follow-up research")
        for f in report.followups:
            print_list_item(f)
    if report.verdict == "accept":
        print_success(f"Report is sound. Safe to absorb: deepr expert absorb '{name}' {report_id}")
    elif report.verdict == "re_research":
        print_warning("Quality is weak; re-research the gaps above before absorbing.")

    # Close the loop: run the follow-ups reflection emitted, budget-bounded.
    if not execute_followups:
        record_completed_reflection_loop(
            profile.name,
            report_id,
            report,
            budget=budget,
            execute_followups=False,
        )
        return
    if execute_followups:
        if not report.followups:
            console.print("[dim]No follow-up queries to execute.[/dim]")
            record_completed_reflection_loop(
                profile.name,
                report_id,
                report,
                budget=budget,
                execute_followups=True,
            )
            return
        from deepr.experts.gap_fill import GapFillEngine, routes_from_queries

        if not yes:
            if not click.confirm(
                f"Run {len(report.followups)} follow-up research quer(ies), ceiling ${budget:.2f}?",
                default=False,
            ):
                print_warning("Follow-ups not executed.")
                record_completed_reflection_loop(
                    profile.name,
                    report_id,
                    report,
                    budget=budget,
                    execute_followups=True,
                    cancelled_followups=True,
                )
                return

        from deepr.experts.loop_lock import expert_verb_lock

        with expert_verb_lock(profile.name, "reflect") as acquired:
            if not acquired:
                from deepr.cli.commands.semantic.expert_reflection_loop import record_reflection_overlap_loop

                print_warning("Reflection follow-ups are already running for this expert.")
                loop_run = record_reflection_overlap_loop(profile.name, report_id, budget=budget)
                console.print(f"[dim]Loop run: {loop_run.run_id} waiting for overlap lock.[/dim]")
                return

            routes = routes_from_queries(report.followups)
            fill = asyncio.run(GapFillEngine(profile).execute(routes, budget=budget, top=len(routes)))

        console.print()
        print_section_header("Follow-up execution")
        for o in fill.outcomes:
            if o.status == "filled":
                console.print(
                    f"  [green]filled[/green]  {o.topic[:70]}  "
                    f"[dim](+{o.absorbed} beliefs, {o.flagged} contested, ${o.cost:.3f})[/dim]"
                )
            else:
                console.print(f"  [yellow]{o.status}[/yellow]  {o.topic[:70]}  [dim]{o.detail[:80]}[/dim]")
        console.print(f"\nTotal cost: ${fill.total_cost:.3f}")
        if any(o.flagged for o in fill.outcomes):
            print_warning(f"Contested beliefs recorded. Review: deepr expert contested '{name}'")
        record_completed_reflection_loop(
            profile.name,
            report_id,
            report,
            budget=budget,
            execute_followups=True,
            fill_result=fill,
        )


@expert.command(name="export-skill")
@click.argument("name")
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=False),
    default=None,
    help="Output directory (default: ./skills/deepr-expert-<slug>/)",
)
@click.option("--print", "print_only", is_flag=True, help="Print the SKILL.md to stdout instead of writing it")
def export_skill(name: str, output: str | None, print_only: bool):
    """Export an expert as a portable agentskills.io SKILL.md.

    Packages the expert as an installable skill for any agentskills.io host
    (Claude Code, Codex CLI, Gemini CLI, VS Code Copilot, Cursor, OpenClaw): the
    generated SKILL.md triggers on the expert's domain and instructs the host
    agent to consult this expert through Deepr's MCP tools. It packages a
    pointer (calls routed over MCP at run time), not a copy of the knowledge, so
    the host needs a running Deepr MCP server with this expert present.

    EXAMPLES:
      deepr expert export-skill "AI Strategy Expert"
      deepr expert export-skill "AI Strategy Expert" -o ~/.claude/skills/ai-strategy
      deepr expert export-skill "AI Strategy Expert" --print
    """
    import sys
    from pathlib import Path

    from deepr.experts.profile import ExpertStore
    from deepr.skills.expert_skill import build_expert_skill, expert_slug

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    packager = build_expert_skill(profile.name, profile.domain or "", profile.description or "")

    if print_only:
        click.echo(packager.render())
        return

    out_dir = Path(output) if output else Path("skills") / f"deepr-expert-{expert_slug(profile.name)}"
    path = packager.generate(out_dir)
    print_success(f"Wrote {path}")
    console.print(
        f"Install: copy [white]{out_dir}[/white] into your agent's skills directory "
        "(e.g. [white]~/.claude/skills/[/white]). The host must have a Deepr MCP server configured."
    )


@expert.command(name="export")
@click.argument("name")
@click.option(
    "--output", "-o", type=click.Path(), default=".", help="Output directory for corpus (default: current directory)"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def export_expert(name: str, output: str, yes: bool):
    """Export an expert's consciousness to a portable corpus.

    Creates a directory containing all the expert's knowledge, beliefs,
    and worldview that can be shared or imported to create a new expert.

    The exported corpus includes:
    - All knowledge documents (markdown files)
    - Worldview (beliefs and knowledge gaps)
    - Metadata (expert profile information)
    - README (human-readable summary)

    EXAMPLES:
      # Export to current directory
      deepr expert export "AWS Expert"

      # Export to specific directory
      deepr expert export "Python Expert" --output ./exports

      # Skip confirmation
      deepr expert export "AI Expert" -y
    """
    import asyncio
    from pathlib import Path

    from deepr.experts.corpus import export_corpus
    from deepr.experts.profile import ExpertStore

    print_header(f"Export Expert: {name}")

    # Load expert
    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        print_error(f"Expert not found: {name}")
        console.print("\nList available experts:")
        console.print("  deepr expert list")
        return

    output_path = Path(output)
    corpus_name = name.lower().replace(" ", "-")
    corpus_path = output_path / corpus_name

    print_key_value("Expert", profile.name)
    print_key_value("Domain", profile.domain or profile.description or "General")
    print_key_value("Documents", str(profile.total_documents))
    print_key_value("Output", str(corpus_path))

    if not yes:
        if not click.confirm("\nExport this expert?"):
            console.print("Cancelled")
            return

    async def do_export():
        try:
            manifest = await export_corpus(name, output_path, store)
            return {"success": True, "manifest": manifest}
        except Exception as e:
            return {"success": False, "error": str(e)}

    result = asyncio.run(do_export())

    if not result["success"]:
        print_error(f"Export failed: {result['error']}")
        return

    manifest = result["manifest"]

    print_header("Export Complete")
    print_key_value("Corpus", str(corpus_path))
    print_key_value("Documents", str(manifest.document_count))
    print_key_value("Beliefs", str(manifest.belief_count))
    print_key_value("Knowledge gaps", str(manifest.gap_count))
    print_key_value("Files", str(len(manifest.files)))
    console.print("\nTo import this corpus:")
    console.print(f'  deepr expert import "New Expert Name" --corpus {corpus_path}')


@expert.command(name="import")
@click.argument("name")
@click.option("--corpus", "-c", type=click.Path(exists=True), required=True, help="Path to corpus directory to import")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def import_expert(name: str, corpus: str, yes: bool):
    """Import a corpus to create a new expert.

    Creates a new expert from an exported corpus, including all documents,
    beliefs, and worldview. The new expert will have the same knowledge
    and understanding as the original.

    EXAMPLES:
      # Import corpus to create new expert
      deepr expert import "My AWS Expert" --corpus ./aws-expert

      # Skip confirmation
      deepr expert import "New Expert" -c ./corpus -y
    """
    import asyncio
    from pathlib import Path

    from deepr.config import AppConfig
    from deepr.experts.corpus import import_corpus, validate_corpus
    from deepr.experts.profile import ExpertStore
    from deepr.providers import create_provider

    print_header(f"Import Expert: {name}")

    corpus_path = Path(corpus)

    # Validate corpus
    validation = validate_corpus(corpus_path)

    if not validation["valid"]:
        print_error("Invalid corpus structure")
        for error in validation["errors"]:
            console.print(f"  [dim]-[/dim] {error}")
        return

    manifest = validation["manifest"]

    # Check if expert already exists
    store = ExpertStore()
    if store.load(name):
        print_error(f"Expert already exists: {name}")
        console.print("\nChoose a different name or delete the existing expert:")
        console.print(f'  deepr expert delete "{name}"')
        return

    print_key_value("Corpus", str(corpus_path))
    print_key_value("Source", manifest.source_expert)
    print_key_value("Domain", manifest.domain)
    print_key_value("Documents", str(manifest.document_count))
    print_key_value("Beliefs", str(manifest.belief_count))
    print_key_value("Knowledge gaps", str(manifest.gap_count))
    print_key_value("New expert name", name)

    if not yes:
        if not click.confirm("\nImport this corpus?"):
            console.print("Cancelled")
            return

    async def do_import():
        try:
            config = AppConfig.from_env()
            provider = create_provider("openai", api_key=config.provider.openai_api_key)

            profile = await import_corpus(name, corpus_path, store, provider)
            return {"success": True, "profile": profile}
        except Exception as e:
            return {"success": False, "error": str(e)}

    console.print("\nImporting...")
    result = asyncio.run(do_import())

    if not result["success"]:
        print_error(f"Import failed: {result['error']}")
        return

    profile = result["profile"]

    print_header("Import Complete")
    print_key_value("Expert created", profile.name)
    print_key_value("Documents", str(profile.total_documents))
    print_key_value("Vector store", profile.vector_store_id)
    console.print(f'\nChat with: deepr chat expert "{name}"')


@expert.command(name="fill-gaps")
@click.argument("name")
@click.option("--budget", "-b", type=float, default=5.0, help="Budget limit for gap filling research (default: $5)")
@click.option("--top", "-t", type=int, default=3, help="Number of top-priority gaps to fill (default: 3)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--api", is_flag=True, help="Allow this legacy metered OpenAI gap-fill path")
@click.option(
    "--confirm-metered-cost",
    is_flag=True,
    help="Allow --yes after reviewing this legacy metered path's cost estimate",
)
@click.option("--consensus", is_flag=True, help="Multi-provider consensus (2-3x cost)")
@click.option("--deep", is_flag=True, help="3-pass pipeline (extract/cross-ref/synthesize)")
@click.option("--validate-citations", is_flag=True, help="Validate source-claim alignment after synthesis")
def fill_gaps(
    name: str,
    budget: float,
    top: int,
    yes: bool,
    api: bool,
    confirm_metered_cost: bool,
    consensus: bool,
    deep: bool,
    validate_citations: bool,
):
    """Proactively research and fill knowledge gaps.

    Reads the expert's worldview, identifies high-priority knowledge gaps,
    researches them using the standard research engine, and re-synthesizes
    the expert's consciousness with the new knowledge.

    This is how experts actively improve themselves - they know what they
    don't know, and can fill those gaps on demand.

    EXAMPLES:
      # Preferred no-surprise path: local or plan-quota first
      deepr expert route-gaps "AWS Expert" --execute --scheduled

      # Explicit legacy metered OpenAI path
      deepr expert fill-gaps "Python Expert" --top 5 --budget 10 --api

      # Skip confirmation only after explicitly acknowledging the metered estimate
      deepr expert fill-gaps "AI Expert" --api -y --confirm-metered-cost
    """
    import asyncio

    from deepr.cli.colors import (
        console,
        get_symbol,
        print_error,
        print_header,
        print_result,
        print_step,
        print_success,
        print_warning,
    )
    from deepr.config import AppConfig
    from deepr.experts.profile import ExpertStore
    from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview
    from deepr.providers import create_provider

    print_header(f"Fill Knowledge Gaps: {name}")

    if not api:
        raise click.UsageError(
            "Legacy `expert fill-gaps` requires --api because it uses metered OpenAI calls. "
            "Prefer `deepr expert route-gaps NAME --execute --local` or "
            "`deepr expert route-gaps NAME --execute --plan BACKEND`."
        )
    if yes and not confirm_metered_cost:
        raise click.UsageError(
            "Legacy metered gap filling with --yes requires --confirm-metered-cost after reviewing the estimate."
        )

    # Load expert
    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        print_error(f"Expert not found: {name}")
        console.print("\nList available experts:")
        console.print("  deepr expert list")
        return

    # Load worldview
    knowledge_dir = store.get_knowledge_dir(name)
    worldview_path = knowledge_dir / "worldview.json"

    if not worldview_path.exists():
        print_error("Expert has no worldview yet.")
        console.print("\nThe expert needs to synthesize knowledge first:")
        console.print(f'  deepr expert refresh "{name}" --synthesize')
        return

    try:
        worldview = Worldview.load(worldview_path)
    except Exception as e:
        print_error(f"Error loading worldview: {e}")
        return

    # Check for gaps
    if not worldview.knowledge_gaps:
        print_success("Expert has no identified knowledge gaps!")
        console.print("\nThe expert's consciousness is complete (for now).")
        console.print(f"Beliefs: {len(worldview.beliefs)}")
        return

    # Sort gaps by priority (highest first)
    sorted_gaps = sorted(worldview.knowledge_gaps, key=lambda g: g.priority, reverse=True)
    gaps_to_fill = sorted_gaps[:top]

    if not gaps_to_fill:
        console.print("No knowledge gaps found to fill.")
        return

    # Calculate budget per gap
    budget_per_gap = budget / len(gaps_to_fill)

    # Display gaps to be filled
    console.print(f"Found {len(worldview.knowledge_gaps)} knowledge gaps.")
    console.print(f"Will fill top {len(gaps_to_fill)} gaps with ${budget:.2f} budget.\n")

    console.print("Gaps to fill:")
    for i, gap in enumerate(gaps_to_fill, 1):
        console.print(f"\n  {i}. {gap.topic} [dim](Priority: {gap.priority}/5)[/dim]")
        if gap.questions:
            console.print("     Questions:")
            for q in gap.questions[:3]:
                console.print(f"       [dim]{get_symbol('sub_bullet')}[/dim] {q}")
            if len(gap.questions) > 3:
                console.print(f"       [dim]... and {len(gap.questions) - 3} more[/dim]")

    console.print(f"\nEstimated metered OpenAI API cost: ~${budget:.2f} (${budget_per_gap:.2f} per gap)")

    if not yes:
        if not click.confirm("\nProceed with gap filling?"):
            console.print("Cancelled")
            return

    async def do_fill_gaps():
        from deepr.experts.chat import ExpertChatSession

        config = AppConfig.from_env()
        provider = create_provider("openai", api_key=config.provider.openai_api_key)

        total_cost = 0.0
        filled_gaps = []
        failed_gaps = []

        # Set up consensus engine if requested
        consensus_engine = None
        if consensus:
            from deepr.experts.consensus import ConsensusEngine

            consensus_engine = ConsensusEngine()
            console.print("[dim]Multi-provider consensus enabled[/dim]")

        # Set up multi-pass pipeline if --deep
        pipeline = None
        if deep:
            from deepr.experts.multi_pass import MultiPassPipeline

            pipeline = MultiPassPipeline(
                client=provider.client,
                consensus_engine=consensus_engine,
            )
            console.print("[dim]3-pass deep pipeline enabled[/dim]")

        # Create a chat session for standard research fallback
        session = ExpertChatSession(profile, budget=budget, agentic=True)

        # Collect existing claims for cross-referencing (used by --deep)
        existing_claims = []
        if deep and worldview.beliefs:
            existing_claims = [b.to_dict() for b in worldview.beliefs[:30]]

        for i, gap in enumerate(gaps_to_fill, 1):
            print_step(i, len(gaps_to_fill), gap.topic)

            # Construct research query from gap
            if gap.questions:
                query = gap.questions[0]
                if len(gap.questions) > 1:
                    query += f" Also address: {'; '.join(gap.questions[1:3])}"
            else:
                query = f"Research and explain: {gap.topic}"

            console.print(f"[dim]Query: {query[:80]}...[/dim]")

            try:
                if pipeline:
                    # Deep 3-pass pipeline
                    console.print(
                        "[dim]Pass 1: Extracting... Pass 2: Cross-referencing... Pass 3: Synthesizing...[/dim]"
                    )
                    mp_result = await pipeline.fill_gap(
                        gap=gap,
                        existing_claims=existing_claims,
                        expert_name=profile.name,
                        domain=profile.domain or profile.description,
                        budget=budget / len(gaps_to_fill),
                        use_consensus=consensus,
                    )
                    cost = mp_result.total_cost
                    total_cost += cost
                    print_result(
                        f"Deep research complete ({mp_result.passes_completed}/3 passes)",
                        cost_usd=cost,
                    )
                    filled_gaps.append({"gap": gap, "cost": cost, "multi_pass": mp_result})

                elif consensus_engine:
                    # Consensus-only (no deep pipeline)
                    console.print("[dim]Researching with consensus...[/dim]")
                    cr = await consensus_engine.research_with_consensus(
                        query=query,
                        budget=budget / len(gaps_to_fill),
                        expert_name=profile.name,
                    )
                    cost = cr.total_cost
                    total_cost += cost
                    print_result(
                        f"Consensus research complete (agreement: {cr.agreement_score:.0%})",
                        cost_usd=cost,
                    )
                    filled_gaps.append({"gap": gap, "cost": cost, "consensus": cr})

                else:
                    # Standard single-provider research
                    console.print("[dim]Researching...[/dim]")
                    result = await session._standard_research(query)

                    if "error" in result:
                        print_error(f"Research failed: {result['error']}")
                        failed_gaps.append({"gap": gap, "error": result["error"]})
                        continue

                    cost = result.get("cost", 0.0)
                    total_cost += cost
                    print_result("Research complete", cost_usd=cost)
                    filled_gaps.append({"gap": gap, "cost": cost})

            except Exception as e:
                print_error(f"Error: {e}")
                failed_gaps.append({"gap": gap, "error": str(e)})

            # Check budget
            if total_cost >= budget:
                print_warning(f"Budget exhausted (${total_cost:.2f}/${budget:.2f})")
                break

        # Re-synthesize consciousness with new knowledge
        if filled_gaps:
            print_header("Re-synthesizing Consciousness")
            console.print("[dim]Expert is integrating new knowledge into beliefs...[/dim]")

            try:
                synthesizer = KnowledgeSynthesizer(provider.client)

                # Get all documents for synthesis
                docs_dir = store.get_documents_dir(name)
                all_docs = list(docs_dir.glob("*.md"))
                docs_to_process = [{"path": str(f)} for f in all_docs[:20]]

                synthesis_result = await synthesizer.synthesize_new_knowledge(
                    expert_name=profile.name,
                    domain=profile.domain or profile.description,
                    new_documents=docs_to_process,
                    existing_worldview=worldview,
                )

                if synthesis_result["success"]:
                    new_worldview = synthesis_result["worldview"]

                    # Remove filled gaps from worldview
                    filled_topics = {g["gap"].topic for g in filled_gaps}
                    new_worldview.knowledge_gaps = [
                        g for g in new_worldview.knowledge_gaps if g.topic not in filled_topics
                    ]

                    # Save updated worldview
                    new_worldview.save(worldview_path)

                    print_success("Synthesis complete!")
                    console.print(f"    New beliefs: {synthesis_result['beliefs_formed']}")
                    console.print(f"    Remaining gaps: {len(new_worldview.knowledge_gaps)}")

                    # Citation validation if requested
                    if validate_citations and synthesis_result.get("worldview"):
                        console.print("[dim]Validating citations...[/dim]")
                        try:
                            from deepr.experts.citation_validator import CitationValidator

                            validator = CitationValidator(client=provider.client)
                            claims = [b.to_claim() for b in new_worldview.beliefs]
                            # Build documents dict from synthesis docs
                            doc_dict = {}
                            for doc_path in all_docs[:20]:
                                try:
                                    doc_dict[doc_path.name] = doc_path.read_text(encoding="utf-8")[:2000]
                                except OSError:
                                    pass
                            validations = await validator.validate_claims(claims, doc_dict)
                            summary = validator.summarize(validations)
                            console.print(
                                f"    Citations validated: {summary['total']} "
                                f"({summary['supported']} supported, "
                                f"{summary['unsupported']} unsupported)"
                            )
                        except Exception as e:
                            print_warning(f"Citation validation error: {e}")

                else:
                    print_warning(f"Synthesis failed: {synthesis_result.get('error', 'Unknown')}")

            except Exception as e:
                print_warning(f"Synthesis error: {e}")

        return {"filled": len(filled_gaps), "failed": len(failed_gaps), "total_cost": total_cost}

    result = asyncio.run(do_fill_gaps())

    # Summary
    print_header("Gap Filling Complete")
    console.print(f"Gaps filled: {result['filled']}/{len(gaps_to_fill)}")
    if result["failed"] > 0:
        console.print(f"Gaps failed: {result['failed']}")
    console.print(f"Total cost: ${result['total_cost']:.4f}")
    console.print("\nExpert consciousness has been updated.")
    console.print(f'Chat with: deepr expert chat "{name}"')


@expert.command(name="validate-citations")
@click.argument("name")
def validate_citations_cmd(name: str):
    """Validate that sources actually support their associated claims.

    Runs semantic citation validation on an expert's claims, classifying
    each source-claim pair as SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / UNCERTAIN.

    EXAMPLES:
      deepr expert validate-citations "AWS Expert"
    """
    import asyncio

    from deepr.config import AppConfig
    from deepr.experts.profile import ExpertStore
    from deepr.experts.synthesis import Worldview
    from deepr.providers import create_provider

    print_header(f"Validate Citations: {name}")

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        return

    knowledge_dir = store.get_knowledge_dir(name)
    worldview_path = knowledge_dir / "worldview.json"
    if not worldview_path.exists():
        print_error("Expert has no worldview yet.")
        return

    try:
        worldview = Worldview.load(worldview_path)
    except Exception as e:
        print_error(f"Error loading worldview: {e}")
        return

    if not worldview.beliefs:
        print_success("Expert has no beliefs to validate.")
        return

    async def do_validate():
        from deepr.experts.citation_validator import CitationValidator

        config = AppConfig.from_env()
        provider = create_provider("openai", api_key=config.provider.openai_api_key)
        validator = CitationValidator(client=provider.client)

        claims = [b.to_claim() for b in worldview.beliefs]
        docs_dir = store.get_documents_dir(name)
        doc_dict = {}
        for doc_path in docs_dir.glob("*.md"):
            try:
                doc_dict[doc_path.name] = doc_path.read_text(encoding="utf-8")[:2000]
            except OSError:
                pass

        validations = await validator.validate_claims(claims, doc_dict)
        return validator.summarize(validations)

    summary = asyncio.run(do_validate())
    console.print(f"Total source-claim pairs: {summary['total']}")
    console.print(f"  Supported:           {summary['supported']}")
    console.print(f"  Partially supported: {summary['partially_supported']}")
    console.print(f"  Unsupported:         {summary['unsupported']}")
    console.print(f"  Uncertain:           {summary['uncertain']}")
    console.print(f"  Support rate:        {summary['support_rate']:.0%}")
    if summary["flagged_claims"]:
        print_warning(f"Flagged claims: {len(summary['flagged_claims'])}")


@expert.command(name="discover-gaps")
@click.argument("name")
def discover_gaps_cmd(name: str):
    """Discover knowledge gaps by analyzing claim coverage.

    Uses embedding-based clustering to find thin knowledge areas,
    then generates gap questions for under-represented topics.

    EXAMPLES:
      deepr expert discover-gaps "Python Expert"
    """
    import asyncio

    from deepr.experts.profile import ExpertStore
    from deepr.experts.synthesis import Worldview

    print_header(f"Discover Gaps: {name}")

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        return

    knowledge_dir = store.get_knowledge_dir(name)
    worldview_path = knowledge_dir / "worldview.json"
    if not worldview_path.exists():
        print_error("Expert has no worldview yet.")
        return

    try:
        worldview = Worldview.load(worldview_path)
    except Exception as e:
        print_error(f"Error loading worldview: {e}")
        return

    if not worldview.beliefs:
        print_warning("Expert has no beliefs to analyze.")
        return

    async def do_discover():
        from deepr.experts.gap_discovery import GapDiscoverer

        discoverer = GapDiscoverer()
        claims = [b.to_claim().to_dict() for b in worldview.beliefs]
        existing_gaps = [g.to_dict() for g in worldview.knowledge_gaps]
        return await discoverer.discover_gaps(claims, profile.domain or "", existing_gaps)

    new_gaps = asyncio.run(do_discover())

    if not new_gaps:
        print_success("No new gaps discovered. Knowledge coverage is good!")
        return

    console.print(f"Discovered {len(new_gaps)} new gaps:\n")
    for i, gap in enumerate(new_gaps, 1):
        method = gap.get("discovery_method", "unknown")
        console.print(f"  {i}. {gap['topic']} [dim][{method}][/dim]")
        for q in gap.get("questions", [])[:2]:
            console.print(f"     - {q}")
    print_success(f"Found {len(new_gaps)} gaps. Use route-gaps --execute --scheduled to fill them safely.")


@expert.command(name="resolve-conflicts")
@click.argument("name")
@click.option("--budget", "-b", type=float, default=5.0, help="Budget for conflict resolution")
@click.option("--consensus", is_flag=True, help="Use multi-provider consensus for adjudication")
def resolve_conflicts_cmd(name: str, budget: float, consensus: bool):
    """Detect and resolve contradictions in expert beliefs.

    Uses heuristic and LLM-based detection to find contradicting beliefs,
    then resolves them via multi-provider adjudication.

    EXAMPLES:
      deepr expert resolve-conflicts "AI Expert"
      deepr expert resolve-conflicts "AI Expert" --consensus --budget 10
    """
    import asyncio

    from deepr.config import AppConfig
    from deepr.experts.profile import ExpertStore
    from deepr.experts.synthesis import Worldview
    from deepr.providers import create_provider

    print_header(f"Resolve Conflicts: {name}")

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        return

    knowledge_dir = store.get_knowledge_dir(name)
    worldview_path = knowledge_dir / "worldview.json"
    if not worldview_path.exists():
        print_error("Expert has no worldview yet.")
        return

    try:
        worldview = Worldview.load(worldview_path)
    except Exception as e:
        print_error(f"Error loading worldview: {e}")
        return

    if not worldview.beliefs:
        print_warning("Expert has no beliefs to check.")
        return

    async def do_resolve():
        from deepr.experts.beliefs import Belief as BeliefObj
        from deepr.experts.conflict_resolver import ConflictResolver

        consensus_engine = None
        if consensus:
            from deepr.experts.consensus import ConsensusEngine

            consensus_engine = ConsensusEngine()

        config = AppConfig.from_env()
        provider = create_provider("openai", api_key=config.provider.openai_api_key)
        resolver = ConflictResolver(consensus_engine=consensus_engine, client=provider.client)

        # Convert synthesis Beliefs to beliefs.py Belief objects
        belief_objects = []
        for b in worldview.beliefs:
            belief_objects.append(
                BeliefObj(
                    claim=b.statement,
                    confidence=b.confidence,
                    evidence_refs=b.evidence,
                    domain=b.topic,
                )
            )

        return await resolver.resolve_all(belief_objects, budget=budget)

    results = asyncio.run(do_resolve())

    if not results:
        print_success("No contradictions found!")
        return

    console.print(f"Resolved {len(results)} contradictions:\n")
    for r in results:
        console.print(f"  Outcome: {r.outcome}")
        console.print(f"  Explanation: {r.explanation[:100]}")
        console.print("")


@expert.command(name="refresh")
@click.argument("name")
@click.option(
    "--synthesize",
    is_flag=True,
    default=False,
    help="Synthesize knowledge after refresh (expert actively processes documents)",
)
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompts")
def refresh_expert(name: str, synthesize: bool, yes: bool):
    """Refresh expert's knowledge by adding new documents from their folder.

    Scans the expert's documents directory and uploads any new files
    that aren't already in the vector store. This closes the learning loop
    so experts actually learn from research results.

    With --synthesize flag, the expert actively processes documents to form
    beliefs, connections, and meta-awareness (Level 5 consciousness).

    Examples:
        deepr expert refresh "Agentic Digital Consciousness"
        deepr expert refresh "Azure Architect" --synthesize
    """
    import asyncio

    from deepr.experts.profile import ExpertStore

    print_header(f"Refreshing Expert Knowledge: {name}")

    async def do_refresh():
        store = ExpertStore()

        try:
            results = await store.refresh_expert_knowledge(name)

            console.print(results["message"])
            console.print()

            if results["uploaded"]:
                print_success(f"Uploaded {len(results['uploaded'])} new documents:")
                for item in results["uploaded"]:
                    import os

                    basename = os.path.basename(item["path"])
                    console.print(f"  [dim]-[/dim] {basename}")
                    console.print(f"    [dim]File ID:[/dim] {item['file_id']}")
                console.print()

            if results["failed"]:
                print_warning(f"Failed to upload {len(results['failed'])} documents:")
                for item in results["failed"]:
                    import os

                    basename = os.path.basename(item["path"])
                    console.print(f"  [dim]-[/dim] {basename}: {item['error']}")
                console.print()

            if not results["uploaded"] and not results["failed"]:
                print_success("Expert knowledge is up to date")
                console.print()

            # Show updated stats
            profile = store.load(name)
            if profile:
                print_key_value("Documents in knowledge base", str(profile.total_documents))
                last_refresh = profile.last_knowledge_refresh
                print_key_value(
                    "Last refreshed",
                    last_refresh.strftime("%Y-%m-%d %H:%M:%S") if last_refresh else "never",
                )

            # Synthesize if requested
            if synthesize and (
                results["uploaded"] or yes or click.confirm("\nNo new documents. Synthesize existing knowledge anyway?")
            ):
                print_section_header("Synthesizing Knowledge (Level 5 Consciousness)")
                console.print("Expert is actively processing documents to form beliefs and meta-awareness...")
                console.print("This may take 1-2 minutes...\n")

                from deepr.config import AppConfig
                from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview
                from deepr.providers import create_provider

                # Get client
                config = AppConfig.from_env()
                provider = create_provider("openai", api_key=config.provider.openai_api_key)
                client = provider.client

                synthesizer = KnowledgeSynthesizer(client)

                # Load existing worldview if exists
                knowledge_dir = store.get_knowledge_dir(name)
                knowledge_dir.mkdir(parents=True, exist_ok=True)
                worldview_path = knowledge_dir / "worldview.json"

                existing_worldview = None
                if worldview_path.exists():
                    try:
                        existing_worldview = Worldview.load(worldview_path)
                        console.print(
                            f"[dim]Loaded existing worldview ({existing_worldview.synthesis_count} prior syntheses)[/dim]"
                        )
                    except Exception as e:
                        print_warning(f"Could not load existing worldview: {e}")

                # Get documents to synthesize (uploaded or all if no new uploads)
                if results["uploaded"]:
                    docs_to_process = [{"path": item["path"]} for item in results["uploaded"]]
                else:
                    # Synthesize all documents
                    docs_dir = store.get_documents_dir(name)
                    all_docs = list(docs_dir.glob("*.md"))
                    docs_to_process = [{"path": str(f)} for f in all_docs[:10]]  # Limit to 10 for cost

                console.print(f"Processing {len(docs_to_process)} documents...\n")

                # Synthesize
                from datetime import datetime

                synthesis_result = await synthesizer.synthesize_new_knowledge(
                    expert_name=profile.name,
                    domain=profile.domain or profile.description,
                    new_documents=docs_to_process,
                    existing_worldview=existing_worldview,
                )

                if synthesis_result["success"]:
                    worldview = synthesis_result["worldview"]
                    reflection = synthesis_result["reflection"]

                    # Save worldview
                    worldview.save(worldview_path)

                    # Generate and save worldview document
                    worldview_doc = await synthesizer.generate_worldview_document(worldview, reflection)

                    worldview_doc_path = knowledge_dir / f"worldview_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.md"
                    with open(worldview_doc_path, "w", encoding="utf-8") as f:
                        f.write(worldview_doc)

                    print_success("Synthesis complete!")
                    click.echo(f"\nBeliefs formed: {synthesis_result['beliefs_formed']}")
                    click.echo(f"Knowledge gaps identified: {synthesis_result['gaps_identified']}")
                    click.echo(f"\nWorldview saved to: {worldview_path.name}")
                    click.echo(f"Reflection saved to: {worldview_doc_path.name}")

                    # Show sample beliefs
                    if worldview.beliefs:
                        click.echo("\nTop beliefs:")
                        for belief in sorted(worldview.beliefs, key=lambda b: b.confidence, reverse=True)[:3]:
                            click.echo(f"  - {belief.statement[:80]}... ({belief.confidence:.0%} confidence)")

                else:
                    print_error(f"Synthesis failed: {synthesis_result.get('error', 'Unknown error')}")

        except ValueError as e:
            print_error(f"Error: {e}")
        except Exception as e:
            print_error(f"Unexpected error: {e}")
            import traceback

            traceback.print_exc()

    asyncio.run(do_refresh())
    click.echo()


@expert.command(name="chat")
@click.argument("name")
@click.option("--budget", "-b", type=float, default=5.0, help="Session budget limit for research (default: $5)")
@click.option(
    "--no-research", is_flag=True, default=False, help="Disable agentic research (experts can research by default)"
)
def chat_with_expert(name: str, budget: float | None, no_research: bool):
    """Start an interactive chat session with an expert.

    Chat with a domain expert using their knowledge base. The expert will
    answer questions based on their accumulated knowledge and cite sources.

    The expert provides "Glass Box" transparency:
    - Every answer cites exact sources with filenames
    - Reasoning traces show what was searched and why
    - Full audit trail for accountability

    Examples:
        deepr expert chat "AWS Solutions Architect"
        deepr expert chat "Python Expert" --budget 5
        deepr expert chat "Python Expert" --no-research  # Disable research

    Commands during chat:
        /quit or /exit - End the session
        /status - Show session statistics and costs
        /clear - Clear conversation history
        /trace - Show reasoning trace (what the expert searched and why)
        /learn <file_path> - Upload a document to expert's knowledge base
        /synthesize - Trigger consciousness synthesis (form beliefs from recent learning)
    """
    import asyncio
    from datetime import datetime

    from deepr.cli import ui
    from deepr.cli.validation import validate_budget
    from deepr.experts.chat import start_chat_session

    # Validate budget - warns for high amounts, doesn't hard block
    try:
        budget = validate_budget(budget, min_budget=0.1)
    except (click.UsageError, click.Abort) as e:
        if isinstance(e, click.Abort):
            click.echo("Cancelled")
            return
        click.echo(f"Error: {e}", err=True)
        return

    # Start the chat session (agentic by default)
    agentic = not no_research
    try:
        session = asyncio.run(start_chat_session(name, budget, agentic=agentic))
    except ValueError as e:
        ui.print_error(str(e))
        click.echo("List available experts with: deepr expert list")
        return
    except Exception as e:
        ui.print_error(f"Error starting chat session: {e}")
        return

    # Calculate knowledge age
    knowledge_age_days = 0
    if session.expert.knowledge_cutoff_date:
        age_delta = datetime.now(UTC).date() - session.expert.knowledge_cutoff_date.date()
        knowledge_age_days = age_delta.days

    # Display modern welcome message
    ui.print_welcome(
        expert_name=session.expert.name,
        domain=session.expert.domain or session.expert.description or "General",
        documents=session.expert.total_documents,
        updated_date=session.expert.knowledge_cutoff_date.strftime("%Y-%m-%d")
        if session.expert.knowledge_cutoff_date
        else "unknown",
        knowledge_age_days=knowledge_age_days,
    )

    # Command registry for slash commands
    from deepr.experts.command_handlers import dispatch_command
    from deepr.experts.commands import MODE_CONFIGS

    # Interactive chat loop
    while True:
        try:
            # Mode indicator in prompt
            mode_label = MODE_CONFIGS[session.chat_mode]["label"].lower()
            user_input = input(f"You ({mode_label}): ").strip()

            if not user_input:
                continue

            # --- Slash command handling via registry ---
            # Normalise CLI backslash prefix to forward slash
            cmd_input = user_input
            if cmd_input.startswith("\\"):
                cmd_input = "/" + cmd_input[1:]

            if cmd_input.startswith("/"):
                result = asyncio.run(dispatch_command(session, cmd_input, {"cli": True}))
                if result is not None:
                    if result.output:
                        console.print(result.output)
                        console.print()
                    if result.end_session:
                        break
                    if result.export_content:
                        console.print(result.export_content[:2000])
                    continue

                # Fall through for unrecognised /commands - handle legacy ones

            # Legacy commands not in the registry
            if user_input.startswith("/learn ") or user_input.startswith("\\learn "):
                # Extract file path
                file_path = user_input.split(None, 1)[1].strip() if " " in user_input else ""
                if not file_path:
                    print_error("Usage: /learn <file_path>")
                    continue

                import shutil
                from pathlib import Path

                from deepr.experts.profile import ExpertStore

                path = Path(file_path)
                if not path.exists():
                    print_error(f"File not found: {file_path}")
                    continue

                click.echo(f"\n[INFO] Teaching expert about {path.name}...")

                async def upload_document():
                    try:
                        store = ExpertStore()

                        # Copy to expert's documents folder
                        docs_dir = store.get_documents_dir(session.expert.name)
                        docs_dir.mkdir(parents=True, exist_ok=True)
                        dest_path = docs_dir / path.name
                        shutil.copy(path, dest_path)

                        # Upload to vector store
                        results = await store.add_documents_to_vector_store(session.expert, [str(dest_path)])

                        if results["uploaded"]:
                            print_success("Document uploaded to knowledge base")
                            click.echo(f"    Expert now has {session.expert.total_documents + 1} documents")
                            click.echo("\nTip: Use /synthesize to help the expert form beliefs from this knowledge\n")

                            # Reload expert to get updated document count
                            session.expert = store.load(session.expert.name)
                        elif results["failed"]:
                            print_error(f"Failed to upload: {results['failed'][0]['error']}")
                        else:
                            click.echo("[INFO] Document already in knowledge base\n")
                    except Exception as e:
                        print_error(f"Error: {e}")

                asyncio.run(upload_document())
                continue

            elif user_input in ["/synthesize", "\\synthesize"]:
                print_section_header("Synthesizing Consciousness")
                console.print("[dim]Expert is actively processing knowledge to form beliefs...[/dim]")
                console.print("This may take 1-2 minutes...\n")

                async def do_synthesis():
                    try:
                        from deepr.config import AppConfig
                        from deepr.experts.profile import ExpertStore
                        from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview
                        from deepr.providers import create_provider

                        store = ExpertStore()

                        # Get client
                        config = AppConfig.from_env()
                        provider = create_provider("openai", api_key=config.provider.openai_api_key)
                        client = provider.client

                        synthesizer = KnowledgeSynthesizer(client)

                        # Load existing worldview if exists
                        knowledge_dir = store.get_knowledge_dir(session.expert.name)
                        knowledge_dir.mkdir(parents=True, exist_ok=True)
                        worldview_path = knowledge_dir / "worldview.json"

                        existing_worldview = None
                        if worldview_path.exists():
                            try:
                                existing_worldview = Worldview.load(worldview_path)
                                console.print(
                                    f"[dim]Building on {existing_worldview.synthesis_count} prior syntheses[/dim]"
                                )
                            except Exception as e:
                                print_warning(f"Could not load existing worldview: {e}")

                        # Get recent documents (last 10)
                        docs_dir = store.get_documents_dir(session.expert.name)
                        all_docs = sorted(docs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
                        docs_to_process = [{"path": str(f)} for f in all_docs[:10]]

                        console.print(f"Processing {len(docs_to_process)} recent documents...\n")

                        # Synthesize
                        synthesis_result = await synthesizer.synthesize_new_knowledge(
                            expert_name=session.expert.name,
                            domain=session.expert.domain or session.expert.description,
                            new_documents=docs_to_process,
                            existing_worldview=existing_worldview,
                        )

                        if synthesis_result["success"]:
                            worldview = synthesis_result["worldview"]
                            reflection = synthesis_result["reflection"]

                            # Save worldview
                            worldview.save(worldview_path)

                            # Generate and save worldview document
                            from datetime import datetime

                            worldview_doc = await synthesizer.generate_worldview_document(worldview, reflection)

                            worldview_doc_path = (
                                knowledge_dir / f"worldview_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.md"
                            )
                            with open(worldview_doc_path, "w", encoding="utf-8") as f:
                                f.write(worldview_doc)

                            print_success("Synthesis complete!")
                            click.echo(f"\nBeliefs formed: {synthesis_result['beliefs_formed']}")
                            click.echo(f"Knowledge gaps identified: {synthesis_result['gaps_identified']}")

                            # Show top beliefs
                            if worldview.beliefs:
                                click.echo("\nTop beliefs (highest confidence):")
                                for belief in sorted(worldview.beliefs, key=lambda b: b.confidence, reverse=True)[:3]:
                                    click.echo(f"  - {belief.statement[:80]}...")
                                    click.echo(f"    Confidence: {belief.confidence:.0%}")

                            click.echo("\nThe expert's consciousness has evolved.\n")
                        else:
                            print_error(f"Synthesis failed: {synthesis_result.get('error', 'Unknown error')}")

                    except Exception as e:
                        print_error(f"Error: {e}")
                        import traceback

                        traceback.print_exc()

                asyncio.run(do_synthesis())
                continue

            # Reject unrecognised slash/backslash commands
            if cmd_input.startswith("/"):
                print_error(f"Unknown command: {user_input.split()[0]}. Type /help for available commands.")
                continue

            # Check budget before processing
            if budget and session.cost_accumulated >= budget:
                ui.print_error(f"Session budget exhausted (${budget:.2f}). End session or increase budget.")
                break

            # Budget warning before sending (pre-emptive)
            if budget:
                remaining = budget - session.cost_accumulated
                if remaining < budget * 0.2:  # Less than 20% remaining
                    click.echo(f"[!] Budget warning: ${remaining:.2f} remaining\n")

            # Track live status updates
            status_live = None
            current_status = ""

            def update_status(status: str):
                """Update the current status text."""
                nonlocal status_live, current_status

                # Skip duplicate status updates to reduce flashing
                if status == current_status:
                    return

                current_status = status

                # Update live display if active
                if status_live and status_live.is_started:
                    # Import at function level to avoid circular imports
                    import os
                    import sys

                    from rich.spinner import Spinner

                    # Use modern styling with diamond icon
                    spinner_type = "dots" if os.environ.get("WT_SESSION") or sys.platform != "win32" else "line"
                    status_live.update(Spinner(spinner_type, text=f"[cyan]◆[/cyan] [dim]{status}[/dim]"))

            # Collect streamed tokens
            streamed_chunks: list[str] = []

            def on_token(text: str):
                """Handle streamed token - stop spinner and print incrementally."""
                nonlocal status_live
                # Close the spinner on first token
                if status_live and status_live.is_started:
                    status_live.__exit__(None, None, None)
                    # Print expert name header before first token
                    console.print(f"[bold cyan]{session.expert.name}[/bold cyan]")
                    console.print()
                streamed_chunks.append(text)
                console.print(text, end="")

            try:
                # Start live status display
                status_live = ui.print_thinking("Thinking...", with_spinner=True)
                status_live.__enter__()

                # Get response with streaming
                response = asyncio.run(
                    session.send_message_streaming(
                        user_input,
                        token_callback=on_token,
                        status_callback=update_status,
                    )
                )

            finally:
                # Stop live display if still active
                if status_live and status_live.is_started:
                    status_live.__exit__(None, None, None)

            if streamed_chunks:
                # Tokens were already printed incrementally
                console.print()  # Final newline
                console.print()
            else:
                # Fallback: no streaming occurred, render full response
                ui.stream_response(session.expert.name, response)

        except KeyboardInterrupt:
            click.echo("\n\nInterrupted. Ending chat session...")
            break
        except EOFError:
            click.echo("\n\nEnding chat session...")
            break
        except Exception as e:
            print_error(f"Error: {e}")
            console.print()
            continue

    # Final summary
    summary = session.get_session_summary()

    # Save conversation before ending
    if summary["messages_exchanged"] > 0:
        session_id = session.save_conversation()
        print_success(f"Conversation saved: {session_id}")

    print_header("Session Summary")
    print_key_value("Messages", str(summary["messages_exchanged"]))
    print_key_value("Total Cost", f"${summary['cost_accumulated']:.4f}")
    if summary["research_jobs_triggered"] > 0:
        print_key_value("Research Jobs", str(summary["research_jobs_triggered"]))
    console.print()


@expert.command(name="run-skill")
@click.argument("name")
@click.argument("skill_name")
@click.argument("tool_name")
@click.option(
    "--args",
    "tool_args",
    type=str,
    default="{}",
    help='Tool arguments as JSON string (e.g. \'{"data": {"revenue": 100}}\')',
)
def run_skill_cmd(name: str, skill_name: str, tool_name: str, tool_args: str):
    """Run a specific skill tool on an expert directly.

    EXAMPLES:
      deepr expert run-skill "Analyst" financial-data calculate_ratios --args '{"data": {"revenue": 100, "net_income": 20}}'
      deepr expert run-skill "Dev Lead" code-analysis complexity_report --args '{"code": "def foo(): pass"}'
    """
    import asyncio
    import json

    from deepr.experts.profile_store import ExpertStore
    from deepr.experts.skills import SkillExecutor, SkillManager

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        return

    manager = SkillManager(expert_name=name)
    skill_def = manager.get_skill(skill_name)
    if not skill_def:
        print_error(f"Skill not found: {skill_name}")
        return

    installed = getattr(profile, "installed_skills", [])
    if skill_name not in installed:
        print_warning(f"Skill '{skill_name}' is not installed on {name}. Installing now...")
        profile.installed_skills = [*installed, skill_name]
        store.save(profile)

    try:
        args = json.loads(tool_args)
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON arguments: {e}")
        return

    async def do_run():
        executor = SkillExecutor(skill_def, budget_remaining=10.0)
        try:
            result = await executor.execute_tool(tool_name, args)
            return result
        finally:
            await executor.cleanup()

    result = asyncio.run(do_run())
    if "error" in result:
        print_error(f"Tool error: {result['error']}")
    else:
        print_success(f"Result from {skill_name}/{tool_name}:")
        console.print_json(json.dumps(result.get("result", result), indent=2, default=str))


# Maintenance commands (absorb, sync) live in a sibling module so this file
# stays under the size ceiling; importing it registers them on the `expert`
# group (Phase Q3 decomposition).
from deepr.cli.commands.semantic import expert_cleanup as _expert_cleanup  # noqa: F401
from deepr.cli.commands.semantic import expert_consult as _expert_consult  # noqa: F401
from deepr.cli.commands.semantic import expert_consult_quality as _expert_consult_quality  # noqa: F401
from deepr.cli.commands.semantic import expert_consult_traces as _expert_consult_traces  # noqa: F401
from deepr.cli.commands.semantic import expert_gap_routes as _expert_gap_routes  # noqa: F401
from deepr.cli.commands.semantic import expert_loop_status as _expert_loop_status  # noqa: F401
from deepr.cli.commands.semantic import expert_maintenance as _expert_maintenance  # noqa: F401
from deepr.cli.commands.semantic import expert_memory_card as _expert_memory_card  # noqa: F401
from deepr.cli.commands.semantic import expert_okf as _expert_okf  # noqa: F401
from deepr.cli.commands.semantic import expert_portrait as _expert_portrait  # noqa: F401
from deepr.cli.commands.semantic import expert_self_model as _expert_self_model  # noqa: F401
from deepr.cli.commands.semantic import expert_validate_export as _expert_validate_export  # noqa: F401
