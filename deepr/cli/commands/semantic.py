"""Semantic command interface - intent-based commands for natural workflows.

This module provides natural, intent-based commands that map to the underlying
implementation commands in run.py. Users think in terms of "I want to research X"
not "Should I use focus or docs mode?".

Command mapping:
    deepr research  -> Automatically chooses between run focus/docs based on prompt
    deepr learn     -> Maps to run project (multi-phase learning)
    deepr team      -> Maps to run team (multi-perspective analysis)

All flags from the underlying commands are supported.
"""

import click
import asyncio
from typing import Optional
from deepr.cli.commands.run import _run_single, _run_campaign, _run_team
from deepr.cli.colors import print_header, print_section_header, print_success, print_error, print_key_value, console


def detect_research_mode(prompt: str) -> str:
    """Auto-detect whether this is documentation research or focused research.

    Returns:
        "docs" if prompt seems documentation-oriented, "focus" otherwise
    """
    # Keywords that suggest documentation intent
    doc_keywords = [
        "document", "documentation", "docs", "guide", "tutorial",
        "how to", "explain", "api", "reference", "spec", "specification",
        "architecture", "design doc", "readme", "manual"
    ]

    prompt_lower = prompt.lower()

    # Check if prompt contains documentation-related keywords
    for keyword in doc_keywords:
        if keyword in prompt_lower:
            return "docs"

    # Default to focused research
    return "focus"


@click.command()
@click.argument("query")
@click.argument("company_name", required=False)
@click.argument("website", required=False)
@click.option("--model", "-m", default=None, help="Research model to use (defaults based on provider)")
@click.option("--provider", "-p", default=None,
              type=click.Choice(["openai", "azure", "gemini", "xai"]),
              help="Research provider (defaults: deep-research=openai, general=xai)")
@click.option("--no-web", is_flag=True, help="Disable web search")
@click.option("--no-code", is_flag=True, help="Disable code interpreter")
@click.option("--upload", "-u", multiple=True, help="Upload files for context")
@click.option("--scrape", "-s", help="Scrape website for primary source research")
@click.option("--limit", "-l", type=float, help="Cost limit in dollars")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
@click.option("--mode", type=click.Choice(["focus", "docs", "auto"]), default="auto",
              help="Research mode (auto=detect automatically)")
@click.option("--scrape-only", is_flag=True, help="Company research: only scrape, don't submit research job")
def research(
    query: str,
    company_name: Optional[str],
    website: Optional[str],
    model: Optional[str],
    provider: Optional[str],
    no_web: bool,
    no_code: bool,
    upload: tuple,
    scrape: Optional[str],
    limit: Optional[float],
    yes: bool,
    mode: str,
    scrape_only: bool,
):
    """Run research with automatic mode detection.

    Automatically detects whether you need focused research or documentation
    research based on your query. You can override with --mode.

    COMPANY RESEARCH MODE:
        deepr research company "<company_name>" "<website>"

        Runs strategic company research with two phases:
        1. Scrapes company website for fresh content
        2. Submits deep research job with strategic analysis prompt

        Output: Consultant-grade strategic overview with 10 sections
        (Executive Summary, Products/Services, USP, Mission/Vision, History,
        Achievements, Target Audience, Financials, KPIs, SWOT)

    GENERAL RESEARCH EXAMPLES:
        deepr research "Analyze AI code editor market 2025"
        deepr research "Document the authentication flow" --mode docs
        deepr research "Latest quantum computing trends" -m o3-deep-research
        deepr research "Company analysis" --upload data.csv --limit 5.00
        deepr research "Strategic analysis of Acme Corp" --scrape https://acmecorp.com
        deepr research "Query" --provider grok -m grok-4-fast
    """
    from deepr.cli.validation import validate_prompt, validate_upload_files, validate_budget

    # Validate query/prompt length
    try:
        query = validate_prompt(query, max_length=50000, field_name="query")
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    # Validate files if provided
    if upload:
        try:
            upload = tuple(str(f) for f in validate_upload_files(upload))
        except click.UsageError as e:
            click.echo(f"Error: {e}", err=True)
            return

    # Validate budget/limit if provided - warns for high amounts
    if limit is not None:
        try:
            limit = validate_budget(limit, min_budget=0.1)
        except (click.UsageError, click.Abort) as e:
            if isinstance(e, click.Abort):
                click.echo("Cancelled")
                return
            click.echo(f"Error: {e}", err=True)
            return

    # Check if this is company research mode
    if query.lower() == "company":
        if not company_name or not website:
            click.echo("Error: Company research requires both company name and website")
            click.echo("\nUsage:")
            click.echo('  deepr research company "Company Name" "https://company.com"')
            click.echo("\nExample:")
            click.echo('  deepr research company "Driscoll Health System" "https://driscollchildrens.org/"')
            return

        # Run company research workflow
        from deepr.core.company_research import CompanyResearchOrchestrator

        print_header("Strategic Company Research")

        orchestrator = CompanyResearchOrchestrator()
        result = asyncio.run(orchestrator.research_company(
            company_name=company_name,
            website=website,
            model=model,
            provider=provider,
            budget_limit=limit,
            skip_confirmation=yes,
            scrape_only=scrape_only,
        ))

        if not result.get('success'):
            print_error(result.get('error', 'Unknown error'))
            return

        print_header("Company Research Complete")

        if result.get('job_id'):
            print_key_value("Job ID", result['job_id'])
            print_key_value("Scraped Content", result['scraped_file'])
            print_key_value("Pages Captured", str(result['pages_scraped']))
        else:
            print_key_value("Scraped Content", result['scraped_file'])
            print_key_value("Pages Captured", str(result['pages_scraped']))

        return

    # Determine provider and model based on configuration
    import os

    # Determine if this is deep research or general operation
    is_deep_research = model is None or ("deep-research" in model.lower() if model else True)

    # Use defaults from environment if not specified
    if provider is None:
        if is_deep_research:
            provider = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
            operation_type = "deep research"
        else:
            provider = os.getenv("DEEPR_DEFAULT_PROVIDER", "xai")
            operation_type = "general operations"
        click.echo(f"[Using {provider} provider (default for {operation_type})]")

    if model is None:
        if is_deep_research:
            model = os.getenv("DEEPR_DEEP_RESEARCH_MODEL", "o4-mini-deep-research")
        else:
            model = os.getenv("DEEPR_DEFAULT_MODEL", "grok-4-fast")
        click.echo(f"[Using {model} model (default for {provider})]")

    # Handle scraping if requested
    if scrape:
        click.echo(f"\n[Scraping {scrape} for primary source research...]")

        try:
            from deepr.utils.scrape import scrape_website, ScrapeConfig
            import tempfile
            import os

            # Configure scraping (default mode for research)
            config = ScrapeConfig(
                max_pages=20,
                max_depth=2,
                try_selenium=False,  # HTTP only by default, faster
            )

            # Scrape website
            results = scrape_website(
                url=scrape,
                purpose="company research" if mode == "focus" or mode == "auto" else "documentation",
                config=config,
                synthesize=False,  # We'll let deep research handle synthesis
            )

            if results['success']:
                click.echo(f"[Scraped {results['pages_scraped']} pages successfully]")

                # Save scraped content to temporary file for upload
                temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8')
                temp_file.write(f"# Scraped Content from {scrape}\n\n")
                temp_file.write(f"**Scraped {results['pages_scraped']} pages**\n\n")

                for url, content in results['scraped_data'].items():
                    temp_file.write(f"## Source: {url}\n\n")
                    temp_file.write(content)
                    temp_file.write("\n\n---\n\n")

                temp_file.close()

                # Add to upload list
                upload = list(upload) + [temp_file.name]
                click.echo(f"[Scraped content saved and added to research context]\n")
            else:
                click.echo(f"[WARNING: Scraping failed - continuing with web research only]")
                click.echo(f"[Error: {results.get('error', 'Unknown error')}]\n")

        except Exception as e:
            click.echo(f"[WARNING: Scraping failed - {e}]")
            click.echo(f"[Continuing with web research only]\n")

    # Auto-detect mode if set to auto
    if mode == "auto":
        detected_mode = detect_research_mode(query)
        click.echo(f"[Auto-detected mode: {detected_mode}]")
    else:
        detected_mode = mode

    # Modify query for docs mode to optimize for documentation
    if detected_mode == "docs":
        if not query.lower().startswith("create") and not query.lower().startswith("document"):
            query = f"Create comprehensive documentation for: {query}"

    # Call the underlying _run_single implementation
    asyncio.run(_run_single(query, model, provider, no_web, no_code, upload, limit, yes))


@click.command()
@click.argument("topic")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model")
@click.option("--provider", default="openai",
              type=click.Choice(["openai", "azure", "gemini", "xai"]),
              help="Research provider")
@click.option("--lead", default="gpt-5", help="Lead planner model")
@click.option("--phases", "-p", type=int, default=3, help="Number of learning phases")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def learn(
    topic: str,
    model: str,
    provider: str,
    lead: str,
    phases: int,
    yes: bool,
):
    """Learn about a topic through multi-phase research.

    Creates a structured learning path with multiple research phases that build
    on each other. Perfect for deep-diving into new technologies, concepts, or domains.

    Examples:
        deepr learn "Ford EV strategy for 2026"
        deepr learn "Azure Landing Zones" --phases 4
        deepr learn "Rust programming language" -m o3-deep-research
        deepr learn "Machine learning fundamentals"
    """
    click.echo(f"[Learning Mode: Multi-phase research with {phases} phases]")
    asyncio.run(_run_campaign(topic, model, lead, phases, yes))


@click.command()
@click.argument("question")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model")
@click.option("--provider", default="openai",
              type=click.Choice(["openai", "azure", "gemini", "xai"]),
              help="Research provider")
@click.option("--perspectives", "-p", type=int, default=6, help="Number of perspectives")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def team(
    question: str,
    model: str,
    provider: str,
    perspectives: int,
    yes: bool,
):
    """Analyze a question from multiple perspectives (dream team).

    Uses Six Thinking Hats methodology to analyze the question from different
    angles simultaneously. Perfect for complex decisions, strategic questions,
    or situations that need diverse viewpoints.

    Examples:
        deepr team "Should we pivot to enterprise?"
        deepr team "Evaluate merger opportunity" --perspectives 8
        deepr team "Technology decision" -m o3-deep-research
    """
    click.echo(f"[Team Mode: {perspectives} perspectives analyzing in parallel]")
    asyncio.run(_run_team(question, model, perspectives, yes))


@click.group(invoke_without_command=True)
@click.option('--list', '-l', is_flag=True, help='List all experts')
@click.pass_context
def expert(ctx, list):
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
    if list:
        ctx.invoke(list_experts)
    # If no subcommand provided, show help
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@expert.command(name="make")
@click.argument("name")
@click.option("--files", "-f", multiple=True, type=click.Path(exists=True),
              help="Files to include in expert's knowledge base")
@click.option("--description", "-d", help="Description of expert's domain")
@click.option("--provider", "-p", default="openai",
              type=click.Choice(["openai", "azure", "gemini"]),
              help="AI provider for expert")
@click.option("--learn", is_flag=True, default=False,
              help="Generate and execute autonomous learning curriculum")
@click.option("--budget", type=float, default=None,
              help="Budget limit for autonomous learning (requires --learn)")
@click.option("--topics", type=int, default=None,
              help="Total number of topics (auto-calculated if using --docs/--quick/--deep)")
@click.option("--docs", type=int, default=None,
              help="Number of documentation topics (FOCUS, ~$0.25 each)")
@click.option("--quick", type=int, default=None,
              help="Number of quick research topics (FOCUS, ~$0.25 each)")
@click.option("--deep", type=int, default=None,
              help="Number of deep research topics (CAMPAIGN, ~$2.00 each)")
@click.option("--no-discovery", is_flag=True, default=False,
              help="Skip source discovery phase (faster but less comprehensive)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation for autonomous learning")
def make_expert(name: str, files: tuple, description: Optional[str], provider: str,
                learn: bool, budget: Optional[float], topics: Optional[int], 
                docs: Optional[int], quick: Optional[int], deep: Optional[int], 
                no_discovery: bool, yes: bool):
    """Create a new domain expert with a knowledge base.

    Creates an expert that can answer questions based on provided documents
    and conduct autonomous research when they encounter knowledge gaps.

    The expert uses the Model Router (Phase 3a) to optimize costs:
    - Simple queries: GPT-5 with low reasoning effort
    - Moderate queries: GPT-5 with medium reasoning effort
    - Complex queries: GPT-5.2 or deep research models

    EXAMPLES:
      # Create expert from markdown docs
      deepr expert make "Azure Architect" -f docs/*.md

      # Create with description
      deepr expert make "Python Expert" -f guides/*.py -d "Python best practices"

      # Create with autonomous learning
      deepr expert make "AI Expert" -f docs/*.md --learn --budget 10
    """
    import asyncio
    from deepr.experts.profile import ExpertStore, ExpertProfile, get_expert_system_message
    from deepr.config import load_config
    from deepr.providers import create_provider
    from datetime import datetime
    from deepr.cli.validation import validate_upload_files, validate_expert_name, validate_budget

    # Validate expert name
    try:
        name = validate_expert_name(name)
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    # Validate files if provided
    if files:
        try:
            files = tuple(str(f) for f in validate_upload_files(files))
        except click.UsageError as e:
            click.echo(f"Error: {e}", err=True)
            return

    # Validate budget if provided - warns for high amounts but doesn't hard block
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

    click.echo(f"Creating expert: {name}...")

    async def create_expert():
        # Load config
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
            name=f"expert-{name.lower().replace(' ', '-')}",
            file_ids=file_ids
        )

        # Wait for indexing only if there are files
        if files:
            success = await provider_instance.wait_for_vector_store(vector_store.id, timeout=900)
            if not success:
                click.echo("Error: Indexing timed out")
                return None

        # Create expert profile with programmatic system message
        # Set initial knowledge cutoff to now (will be updated when learning is added)
        now = datetime.utcnow()

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
                domain_velocity="medium"  # Default, can be customized later
            ),
            provider=provider
        )

        # Save profile
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
            
            # docs and quick are both FOCUS mode (grok-4-fast: ~$0.002)
            # deep is CAMPAIGN mode (o4-mini-deep-research: ~$1.00)
            calculated_budget = (docs_count * expert_config.quick_research_cost) + (quick_count * expert_config.quick_research_cost) + (deep_count * expert_config.deep_research_cost)
            
            if budget is not None:
                # Mode 3: Validate calculated budget against provided budget
                if calculated_budget > budget:
                    click.echo(f"Error: Calculated budget (${calculated_budget:.2f}) exceeds provided budget (${budget:.2f})")
                    click.echo(f"\nTopic breakdown:")
                    click.echo(f"  {docs_count} docs × ${expert_config.quick_research_cost:.3f} = ${docs_count * expert_config.quick_research_cost:.2f}")
                    click.echo(f"  {quick_count} quick × ${expert_config.quick_research_cost:.3f} = ${quick_count * expert_config.quick_research_cost:.2f}")
                    click.echo(f"  {deep_count} deep × ${expert_config.deep_research_cost:.2f} = ${deep_count * expert_config.deep_research_cost:.2f}")
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
            from deepr.experts.curriculum import CurriculumGenerator
            from deepr.experts.learner import AutonomousLearner
            from deepr.config import AppConfig

            config = AppConfig.from_env()

            click.echo(f"Generating curriculum...")

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
                    enable_discovery=not no_discovery  # Skip discovery if --no-discovery flag is set
                )

                print(f"DEBUG CLI: Received curriculum: {curriculum}")
                print(f"DEBUG CLI: Curriculum type: {type(curriculum)}")
                if curriculum:
                    print(f"DEBUG CLI: Curriculum.topics: {curriculum.topics}")
                    print(f"DEBUG CLI: Number of topics: {len(curriculum.topics) if curriculum.topics else 0}")

                # Display curriculum summary
                if not curriculum or not curriculum.topics:
                    print_error("Curriculum generation failed - no topics created")
                    return {"error": "No topics generated"}
                
                print_header(f"Curriculum: {len(curriculum.topics)} topics")
                
                for i, topic in enumerate(curriculum.topics, 1):
                    console.print(f"{i}. [bold]{topic.title}[/bold]")
                    console.print(f"   [dim]Mode:[/dim] {topic.research_mode} | [dim]Type:[/dim] {topic.research_type}")
                    console.print(f"   [dim]Cost:[/dim] ${topic.estimated_cost:.4f} | [dim]Time:[/dim] ~{topic.estimated_minutes}min")
                    if topic.sources:
                        console.print(f"   [dim]Sources:[/dim] {len(topic.sources)}")
                    console.print()
                
                console.print(f"[dim]Total:[/dim] ${curriculum.total_estimated_cost:.2f}, ~{curriculum.total_estimated_minutes}min\n")
                console.print("Starting execution...")

                # Execute curriculum
                learner = AutonomousLearner(config)

                progress = await learner.execute_curriculum(
                    expert=profile,
                    curriculum=curriculum,
                    budget_limit=budget_to_use,
                    dry_run=False
                )

                return progress

            except Exception as e:
                # Return the error so we can handle it with graceful degradation
                return {"error": e}

        result = asyncio.run(generate_and_execute_curriculum())
        
        # Check if curriculum generation failed
        if result and isinstance(result, dict) and "error" in result:
            error = result["error"]
            click.echo(f"\nError: {str(error)}")
            click.echo(f"Expert created but learning failed. Try again later.")
            return
        
        progress = result

        if progress:
            click.echo(f"\nComplete: {len(progress.completed_topics)}/{len(progress.completed_topics) + len(progress.failed_topics)} topics, ${progress.total_cost:.2f}, {(progress.completed_at - progress.started_at).total_seconds()/60:.0f}min")

    click.echo(f"\nUsage: deepr chat expert \"{profile.name}\"")


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
    from deepr.experts.profile import ExpertStore
    from deepr.cli.colors import print_header, print_info, console

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
        console.print(f"  [bold]{expert.name}[/bold]")
        if expert.description:
            console.print(f"    [dim]{expert.description}[/dim]")
        console.print(f"    Documents: {expert.total_documents}")
        console.print(f"    Conversations: {expert.conversations}")
        if expert.research_triggered > 0:
            console.print(f"    Research: {expert.research_triggered} jobs [yellow](${expert.total_research_cost:.2f})[/yellow]")

        # Show temporal information
        created_str = expert.created_at.strftime('%Y-%m-%d')
        updated_str = expert.updated_at.strftime('%Y-%m-%d')

        if created_str == updated_str:
            console.print(f"    Created: {created_str}")
        else:
            console.print(f"    Created: {created_str}, Updated: {updated_str}")

        # Show knowledge freshness status
        if expert.knowledge_cutoff_date:
            freshness = expert.get_freshness_status()
            age_days = freshness.get('age_days', 0)
            status = freshness.get('status', 'unknown')
            # Color code the status
            if status == 'fresh':
                status_color = 'green'
            elif status == 'recent':
                status_color = 'yellow'
            else:
                status_color = 'red'
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

    from deepr.cli.colors import print_header, print_key_value, print_list_item, console
    
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
    print_key_value("Created", profile.created_at.strftime('%Y-%m-%d %H:%M:%S'))
    print_key_value("Updated", profile.updated_at.strftime('%Y-%m-%d %H:%M:%S'))


@expert.command(name="delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_expert(name: str, yes: bool):
    """Delete an expert and optionally its knowledge base."""
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        click.echo(f"Error: Expert not found: {name}")
        return

    click.echo(f"\nExpert: {profile.name}")
    click.echo(f"Knowledge Base: {profile.vector_store_id}")
    click.echo(f"Documents: {profile.total_documents}")

    if not yes:
        click.echo("\nThis will delete the expert profile.")
        click.echo("Knowledge base (vector store) will remain and must be deleted separately.")
        if not click.confirm("\nDelete expert?"):
            click.echo("Cancelled")
            return

    if store.delete(name):
        print_success(f"Expert deleted: {name}")
        click.echo(f"\nTo delete the knowledge base:")
        click.echo(f"  deepr knowledge delete {profile.vector_store_id}")
    else:
        click.echo(f"\nError: Failed to delete expert")


@expert.command(name="learn")
@click.argument("name")
@click.argument("topic", required=False)
@click.option("--files", "-f", multiple=True, type=click.Path(exists=True),
              help="Files to add to expert's knowledge base")
@click.option("--budget", "-b", type=float, default=1.0,
              help="Budget limit for topic research (default: $1)")
@click.option("--synthesize/--no-synthesize", default=True,
              help="Re-synthesize consciousness after learning (default: yes)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def learn_expert(name: str, topic: Optional[str], files: tuple, budget: float, 
                 synthesize: bool, yes: bool):
    """Add knowledge to an expert on demand.

    Allows you to teach an expert new things by either:
    1. Researching a topic (uses web search to gather information)
    2. Uploading files directly to the knowledge base
    3. Both at the same time

    After adding knowledge, the expert re-synthesizes its consciousness
    to integrate the new information into its beliefs and worldview.

    EXAMPLES:
      # Research a topic and add to expert's knowledge
      deepr expert learn "AWS Expert" "Latest Lambda features 2026"

      # Add files to expert's knowledge base
      deepr expert learn "Python Expert" --files docs/*.md

      # Research topic AND add files
      deepr expert learn "AI Expert" "Transformer architectures" -f papers/*.pdf

      # Research with higher budget
      deepr expert learn "Tech Expert" "Quantum computing advances" --budget 5

      # Skip synthesis (faster, but expert won't form new beliefs)
      deepr expert learn "Expert" "Topic" --no-synthesize
    """
    import asyncio
    import os
    from pathlib import Path
    from deepr.experts.profile import ExpertStore
    from deepr.experts.synthesis import Worldview, KnowledgeSynthesizer
    from deepr.config import AppConfig
    from deepr.providers import create_provider
    from datetime import datetime
    from deepr.cli.validation import validate_budget

    # Validate inputs
    if not topic and not files:
        click.echo("Error: Must provide either a topic to research or files to upload.")
        click.echo("\nExamples:")
        click.echo('  deepr expert learn "Expert Name" "Topic to research"')
        click.echo('  deepr expert learn "Expert Name" --files docs/*.md')
        click.echo('  deepr expert learn "Expert Name" "Topic" -f docs/*.md')
        return

    # Validate budget - warns for high amounts
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

    # Load expert
    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        print_error(f"Expert not found: {name}")
        console.print("\nList available experts:")
        console.print("  deepr expert list")
        return

    # Display what we're going to do
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

        # Phase 1: Research topic if provided
        if topic:
            print_section_header("Phase 1: Researching Topic")

            # Create a chat session for research (agentic mode)
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
                    
                    # Show snippet of what was learned
                    answer = result.get("answer", "")
                    if answer:
                        snippet = answer[:200] + "..." if len(answer) > 200 else answer
                        console.print(f"\n[dim]Learned:[/dim]\n{snippet}")

            except Exception as e:
                print_error(f"Research error: {e}")

        # Phase 2: Upload files if provided
        if files:
            print_section_header("Phase 2: Uploading Files")

            # Get documents directory
            docs_dir = store.get_documents_dir(name)
            docs_dir.mkdir(parents=True, exist_ok=True)

            uploaded_files = []
            for file_path in files:
                try:
                    src_path = Path(file_path)
                    dst_path = docs_dir / src_path.name

                    # Copy file to expert's documents folder
                    import shutil
                    shutil.copy2(src_path, dst_path)
                    uploaded_files.append(dst_path)
                    print_success(f"Copied: {src_path.name}")

                except Exception as e:
                    print_error(f"Failed to copy {file_path}: {e}")

            # Upload to vector store
            if uploaded_files:
                click.echo(f"\nUploading {len(uploaded_files)} files to vector store...")
                
                try:
                    for file_path in uploaded_files:
                        file_id = await provider.upload_document(str(file_path))
                        await provider.add_file_to_vector_store(
                            profile.vector_store_id, 
                            file_id
                        )
                        documents_added += 1
                        console.print(f"[success]Indexed: {file_path.name}[/success]")

                    # Update profile
                    profile.total_documents += len(uploaded_files)
                    profile.source_files.extend([str(f) for f in uploaded_files])
                    profile.updated_at = datetime.utcnow()
                    store.save(profile)

                except Exception as e:
                    print_error(f"Vector store upload failed: {e}")

        # Phase 3: Re-synthesize consciousness
        if synthesize and documents_added > 0:
            print_section_header("Phase 3: Re-synthesizing Consciousness")
            console.print("Expert is integrating new knowledge into beliefs...")

            try:
                synthesizer = KnowledgeSynthesizer(provider.client)

                # Load existing worldview if it exists
                knowledge_dir = store.get_knowledge_dir(name)
                worldview_path = knowledge_dir / "worldview.json"
                existing_worldview = None
                
                if worldview_path.exists():
                    try:
                        existing_worldview = Worldview.load(worldview_path)
                    except Exception:
                        pass  # Will create new worldview

                # Get all documents for synthesis
                docs_dir = store.get_documents_dir(name)
                all_docs = list(docs_dir.glob("*.md"))
                docs_to_process = [{"path": str(f)} for f in all_docs[:20]]  # Limit to 20

                synthesis_result = await synthesizer.synthesize_new_knowledge(
                    expert_name=profile.name,
                    domain=profile.domain or profile.description,
                    new_documents=docs_to_process,
                    existing_worldview=existing_worldview
                )

                if synthesis_result["success"]:
                    new_worldview = synthesis_result["worldview"]
                    new_worldview.save(worldview_path)

                    # Also save markdown version
                    worldview_md_path = knowledge_dir / "worldview.md"
                    new_worldview.save_markdown(worldview_md_path)

                    print_success("Synthesis complete!")
                    click.echo(f"    Beliefs: {len(new_worldview.beliefs)}")
                    click.echo(f"    Knowledge gaps: {len(new_worldview.knowledge_gaps)}")
                    
                    if synthesis_result.get('beliefs_formed', 0) > 0:
                        click.echo(f"    New beliefs formed: {synthesis_result['beliefs_formed']}")
                else:
                    console.print(f"[warning]Synthesis failed: {synthesis_result.get('error', 'Unknown')}[/warning]")

            except Exception as e:
                console.print(f"[warning]Synthesis error: {e}[/warning]")

        return {
            "documents_added": documents_added,
            "total_cost": total_cost,
            "research_results": len(research_results)
        }

    result = asyncio.run(do_learn())

    # Summary
    print_header("Learning Complete")
    print_key_value("Documents added", str(result['documents_added']))
    if result['research_results'] > 0:
        print_key_value("Research queries", str(result['research_results']))
    print_key_value("Total cost", f"${result['total_cost']:.4f}")
    
    if synthesize and result['documents_added'] > 0:
        console.print("\nExpert consciousness has been updated.")
    elif result['documents_added'] > 0:
        console.print("\nKnowledge added. Run with --synthesize to update consciousness.")
    
    console.print(f'\nChat with: deepr chat expert "{name}"')


@expert.command(name="resume")
@click.argument("name")
@click.option("--budget", "-b", type=float, default=None,
              help="Budget limit for remaining topics (default: use original budget)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def resume_expert_learning(name: str, budget: Optional[float], yes: bool):
    """Resume paused learning for an expert.

    When autonomous learning hits a daily or monthly spending limit, progress
    is automatically saved. Use this command to resume where you left off.

    The command will:
    1. Load saved progress (completed topics, remaining topics)
    2. Continue with remaining topics
    3. Clear saved progress on successful completion

    EXAMPLES:
      # Resume learning for an expert
      deepr expert resume "AWS Expert"

      # Resume with a different budget
      deepr expert resume "AWS Expert" --budget 10

      # Skip confirmation
      deepr expert resume "AWS Expert" -y
    """
    import asyncio
    from deepr.experts.profile import ExpertStore
    from deepr.experts.learner import AutonomousLearner
    from deepr.experts.curriculum import LearningCurriculum, LearningTopic
    from deepr.config import AppConfig
    from deepr.cli.validation import validate_budget, validate_expert_name
    from datetime import datetime

    # Validate expert name
    try:
        name = validate_expert_name(name)
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    print_header(f"Resume Learning: {name}")

    # Load expert
    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        print_error(f"Expert not found: {name}")
        console.print("\nList available experts:")
        console.print("  deepr expert list")
        return

    # Load saved progress
    config = AppConfig.from_env()
    learner = AutonomousLearner(config)
    saved_progress = learner.load_learning_progress(name)

    if not saved_progress:
        print_error("No saved progress found for this expert")
        console.print("\nThis expert has no paused learning session to resume.")
        console.print("To start new learning, use:")
        console.print(f'  deepr expert learn "{name}" "topic to research"')
        return

    # Display saved progress info
    remaining_topics = saved_progress.get('remaining_topics', [])
    completed_topics = saved_progress.get('completed_topics', [])
    failed_topics = saved_progress.get('failed_topics', [])
    cost_so_far = saved_progress.get('total_cost_so_far', 0.0)
    paused_at = saved_progress.get('paused_at', 'unknown')

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
    estimated_remaining_cost = sum(t.get('estimated_cost', 0.5) for t in remaining_topics)
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
                title=t.get('title', 'Unknown'),
                research_prompt=t.get('research_prompt', ''),
                research_mode=t.get('research_mode', 'focus'),
                research_type=t.get('research_type', 'general'),
                estimated_cost=t.get('estimated_cost', 0.5),
                estimated_minutes=t.get('estimated_minutes', 5)
            )
            topics.append(topic)

        curriculum = LearningCurriculum(
            expert_name=name,
            domain=profile.domain or profile.description or name,
            topics=topics,
            total_estimated_cost=estimated_remaining_cost,
            total_estimated_minutes=sum(t.get('estimated_minutes', 5) for t in remaining_topics)
        )

        # Execute with resume=True
        progress = await learner.execute_curriculum(
            expert=profile,
            curriculum=curriculum,
            budget_limit=budget,
            dry_run=False,
            resume=True
        )

        return progress

    progress = asyncio.run(do_resume())

    if progress:
        print_header("Resume Complete")
        print_key_value("Completed", f"{len(progress.completed_topics)} topics")
        print_key_value("Failed", f"{len(progress.failed_topics)} topics")
        print_key_value("Total cost", f"${progress.total_cost:.2f}")
        print_key_value("Success rate", f"{progress.success_rate()*100:.1f}%")

        if progress.is_complete():
            console.print("\nAll topics processed. Learning complete.")
        else:
            console.print("\nSome topics remain. Run again to continue:")
            console.print(f'  deepr expert resume "{name}"')

    console.print(f'\nChat with: deepr chat expert "{name}"')


@expert.command(name="export")
@click.argument("name")
@click.option("--output", "-o", type=click.Path(), default=".",
              help="Output directory for corpus (default: current directory)")
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
    from deepr.experts.profile import ExpertStore
    from deepr.experts.corpus import export_corpus

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
    print_key_value("Domain", profile.domain or profile.description or 'General')
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
    console.print(f"\nTo import this corpus:")
    console.print(f'  deepr expert import "New Expert Name" --corpus {corpus_path}')


@expert.command(name="import")
@click.argument("name")
@click.option("--corpus", "-c", type=click.Path(exists=True), required=True,
              help="Path to corpus directory to import")
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
    from deepr.experts.profile import ExpertStore
    from deepr.experts.corpus import import_corpus, validate_corpus, CorpusManifest
    from deepr.config import AppConfig
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
@click.option("--budget", "-b", type=float, default=5.0,
              help="Budget limit for gap filling research (default: $5)")
@click.option("--top", "-t", type=int, default=3,
              help="Number of top-priority gaps to fill (default: 3)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def fill_gaps(name: str, budget: float, top: int, yes: bool):
    """Proactively research and fill knowledge gaps.

    Reads the expert's worldview, identifies high-priority knowledge gaps,
    researches them using the standard research engine, and re-synthesizes
    the expert's consciousness with the new knowledge.

    This is how experts actively improve themselves - they know what they
    don't know, and can fill those gaps on demand.

    EXAMPLES:
      # Fill top 3 gaps with $5 budget
      deepr expert fill-gaps "AWS Expert"

      # Fill top 5 gaps with $10 budget
      deepr expert fill-gaps "Python Expert" --top 5 --budget 10

      # Skip confirmation
      deepr expert fill-gaps "AI Expert" -y
    """
    import asyncio
    from deepr.experts.profile import ExpertStore
    from deepr.experts.synthesis import Worldview, KnowledgeSynthesizer
    from deepr.config import AppConfig
    from deepr.providers import create_provider
    from datetime import datetime
    from deepr.cli.colors import (
        print_header, print_success, print_error, print_warning, 
        print_info, print_step, print_result, get_symbol, console
    )

    print_header(f"Fill Knowledge Gaps: {name}")

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
        print_error(f"Expert has no worldview yet.")
        console.print(f"\nThe expert needs to synthesize knowledge first:")
        console.print(f'  deepr expert refresh "{name}" --synthesize')
        return

    try:
        worldview = Worldview.load(worldview_path)
    except Exception as e:
        print_error(f"Error loading worldview: {e}")
        return

    # Check for gaps
    if not worldview.knowledge_gaps:
        print_success(f"Expert has no identified knowledge gaps!")
        console.print(f"\nThe expert's consciousness is complete (for now).")
        console.print(f"Beliefs: {len(worldview.beliefs)}")
        return

    # Sort gaps by priority (highest first)
    sorted_gaps = sorted(worldview.knowledge_gaps, key=lambda g: g.priority, reverse=True)
    gaps_to_fill = sorted_gaps[:top]

    # Calculate budget per gap
    budget_per_gap = budget / len(gaps_to_fill)

    # Display gaps to be filled
    console.print(f"Found {len(worldview.knowledge_gaps)} knowledge gaps.")
    console.print(f"Will fill top {len(gaps_to_fill)} gaps with ${budget:.2f} budget.\n")

    console.print("Gaps to fill:")
    for i, gap in enumerate(gaps_to_fill, 1):
        console.print(f"\n  {i}. {gap.topic} [dim](Priority: {gap.priority}/5)[/dim]")
        if gap.questions:
            console.print(f"     Questions:")
            for q in gap.questions[:3]:
                console.print(f"       [dim]{get_symbol('sub_bullet')}[/dim] {q}")
            if len(gap.questions) > 3:
                console.print(f"       [dim]... and {len(gap.questions) - 3} more[/dim]")

    console.print(f"\nEstimated cost: ~${budget:.2f} (${budget_per_gap:.2f} per gap)")

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

        # Create a chat session for research (agentic mode)
        session = ExpertChatSession(profile, budget=budget, agentic=True)

        for i, gap in enumerate(gaps_to_fill, 1):
            print_step(i, len(gaps_to_fill), gap.topic)

            # Construct research query from gap
            if gap.questions:
                # Use the first question as the main query
                query = gap.questions[0]
                if len(gap.questions) > 1:
                    # Add context from other questions
                    query += f" Also address: {'; '.join(gap.questions[1:3])}"
            else:
                query = f"Research and explain: {gap.topic}"

            console.print(f"[dim]Query: {query[:80]}...[/dim]")

            try:
                # Use standard research to fill the gap
                console.print("[dim]Researching...[/dim]")
                result = await session._standard_research(query)

                if "error" in result:
                    print_error(f"Research failed: {result['error']}")
                    failed_gaps.append({"gap": gap, "error": result['error']})
                else:
                    cost = result.get("cost", 0.0)
                    total_cost += cost
                    print_result("Research complete", cost_usd=cost)

                    # The research is automatically added to knowledge base
                    # by _standard_research via _add_research_to_knowledge_base
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
                docs_to_process = [{"path": str(f)} for f in all_docs[:20]]  # Limit to 20

                synthesis_result = await synthesizer.synthesize_new_knowledge(
                    expert_name=profile.name,
                    domain=profile.domain or profile.description,
                    new_documents=docs_to_process,
                    existing_worldview=worldview
                )

                if synthesis_result["success"]:
                    new_worldview = synthesis_result["worldview"]

                    # Remove filled gaps from worldview
                    filled_topics = {g["gap"].topic for g in filled_gaps}
                    new_worldview.knowledge_gaps = [
                        g for g in new_worldview.knowledge_gaps
                        if g.topic not in filled_topics
                    ]

                    # Save updated worldview
                    new_worldview.save(worldview_path)

                    print_success("Synthesis complete!")
                    console.print(f"    New beliefs: {synthesis_result['beliefs_formed']}")
                    console.print(f"    Remaining gaps: {len(new_worldview.knowledge_gaps)}")
                else:
                    print_warning(f"Synthesis failed: {synthesis_result.get('error', 'Unknown')}")

            except Exception as e:
                print_warning(f"Synthesis error: {e}")

        return {
            "filled": len(filled_gaps),
            "failed": len(failed_gaps),
            "total_cost": total_cost
        }

    result = asyncio.run(do_fill_gaps())

    # Summary
    print_header("Gap Filling Complete")
    console.print(f"Gaps filled: {result['filled']}/{len(gaps_to_fill)}")
    if result['failed'] > 0:
        console.print(f"Gaps failed: {result['failed']}")
    console.print(f"Total cost: ${result['total_cost']:.4f}")
    console.print(f"\nExpert consciousness has been updated.")
    console.print(f'Chat with: deepr expert chat "{name}"')


@expert.command(name="refresh")
@click.argument("name")
@click.option("--synthesize", is_flag=True, default=False,
              help="Synthesize knowledge after refresh (expert actively processes documents)")
@click.option("--yes", "-y", is_flag=True, default=False,
              help="Skip confirmation prompts")
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
                print_key_value("Last refreshed", profile.last_knowledge_refresh.strftime('%Y-%m-%d %H:%M:%S'))

            # Synthesize if requested
            if synthesize and (results["uploaded"] or yes or click.confirm("\nNo new documents. Synthesize existing knowledge anyway?")):
                print_section_header("Synthesizing Knowledge (Level 5 Consciousness)")
                console.print("Expert is actively processing documents to form beliefs and meta-awareness...")
                console.print("This may take 1-2 minutes...\n")

                from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview
                from deepr.config import AppConfig
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
                        console.print(f"[dim]Loaded existing worldview ({existing_worldview.synthesis_count} prior syntheses)[/dim]")
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
                synthesis_result = await synthesizer.synthesize_new_knowledge(
                    expert_name=profile.name,
                    domain=profile.domain or profile.description,
                    new_documents=docs_to_process,
                    existing_worldview=existing_worldview
                )

                if synthesis_result["success"]:
                    worldview = synthesis_result["worldview"]
                    reflection = synthesis_result["reflection"]

                    # Save worldview
                    worldview.save(worldview_path)

                    # Generate and save worldview document
                    worldview_doc = await synthesizer.generate_worldview_document(
                        worldview, reflection
                    )

                    worldview_doc_path = knowledge_dir / f"worldview_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
                    with open(worldview_doc_path, 'w', encoding='utf-8') as f:
                        f.write(worldview_doc)

                    print_success("Synthesis complete!")
                    click.echo(f"\nBeliefs formed: {synthesis_result['beliefs_formed']}")
                    click.echo(f"Knowledge gaps identified: {synthesis_result['gaps_identified']}")
                    click.echo(f"\nWorldview saved to: {worldview_path.name}")
                    click.echo(f"Reflection saved to: {worldview_doc_path.name}")

                    # Show sample beliefs
                    if worldview.beliefs:
                        click.echo(f"\nTop beliefs:")
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

    from datetime import datetime
    asyncio.run(do_refresh())
    click.echo()


@expert.command(name="chat")
@click.argument("name")
@click.option("--budget", "-b", type=float, default=5.0,
              help="Session budget limit for research (default: $5)")
@click.option("--no-research", is_flag=True, default=False,
              help="Disable agentic research (experts can research by default)")
def chat_with_expert(name: str, budget: Optional[float], no_research: bool):
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
    from deepr.experts.chat import start_chat_session
    from deepr.cli import ui
    from deepr.cli.validation import validate_budget
    from datetime import datetime

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
        age_delta = datetime.now().date() - session.expert.knowledge_cutoff_date.date()
        knowledge_age_days = age_delta.days

    # Display modern welcome message
    ui.print_welcome(
        expert_name=session.expert.name,
        domain=session.expert.domain or session.expert.description or 'General',
        documents=session.expert.total_documents,
        updated_date=session.expert.knowledge_cutoff_date.strftime('%Y-%m-%d') if session.expert.knowledge_cutoff_date else 'unknown',
        knowledge_age_days=knowledge_age_days
    )

    # Interactive chat loop
    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input in ["/quit", "/exit"]:
                ui.console.print("\n[dim]Ending chat session...[/dim]")
                ui.print_session_summary(
                    messages_count=len([m for m in session.messages if m["role"] == "user"]),
                    cost=session.cost_accumulated,
                    research_jobs=len(session.research_jobs),
                    model=session.expert.model
                )
                break

            elif user_input == "/help":
                ui.print_command_help()
                continue

            elif user_input == "/status":
                summary = session.get_session_summary()
                ui.print_status(
                    expert_name=session.expert.name,
                    messages_count=summary['messages_exchanged'],
                    cost=summary['cost_accumulated'],
                    budget=budget,
                    research_jobs=summary['research_jobs_triggered'],
                    model=summary['model'],
                    documents=session.expert.total_documents,
                    daily_spent=summary.get('daily_spent', 0),
                    daily_limit=summary.get('daily_limit', 0),
                    monthly_spent=summary.get('monthly_spent', 0),
                    monthly_limit=summary.get('monthly_limit', 0)
                )
                continue

            elif user_input == "/clear":
                session.messages = []
                console.print("\n[success]Conversation history cleared[/success]\n")
                continue

            elif user_input == "/trace":
                ui.print_trace(session.reasoning_trace)
                continue

            elif user_input.startswith("/learn "):
                # Extract file path
                file_path = user_input[7:].strip()
                if not file_path:
                    print_error("Usage: /learn <file_path>")
                    continue

                from pathlib import Path
                from deepr.experts.profile import ExpertStore
                import shutil

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
                        results = await store.add_documents_to_vector_store(
                            session.expert, [str(dest_path)]
                        )

                        if results["uploaded"]:
                            print_success("Document uploaded to knowledge base")
                            click.echo(f"    Expert now has {session.expert.total_documents + 1} documents")
                            click.echo(f"\nTip: Use /synthesize to help the expert form beliefs from this knowledge\n")

                            # Reload expert to get updated document count
                            session.expert = store.load(session.expert.name)
                        elif results["failed"]:
                            print_error(f"Failed to upload: {results['failed'][0]['error']}")
                        else:
                            click.echo(f"[INFO] Document already in knowledge base\n")
                    except Exception as e:
                        print_error(f"Error: {e}")

                asyncio.run(upload_document())
                continue

            elif user_input == "/synthesize":
                print_section_header("Synthesizing Consciousness")
                console.print("[dim]Expert is actively processing knowledge to form beliefs...[/dim]")
                console.print("This may take 1-2 minutes...\n")

                async def do_synthesis():
                    try:
                        from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview
                        from deepr.experts.profile import ExpertStore
                        from deepr.config import AppConfig
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
                                console.print(f"[dim]Building on {existing_worldview.synthesis_count} prior syntheses[/dim]")
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
                            existing_worldview=existing_worldview
                        )

                        if synthesis_result["success"]:
                            worldview = synthesis_result["worldview"]
                            reflection = synthesis_result["reflection"]

                            # Save worldview
                            worldview.save(worldview_path)

                            # Generate and save worldview document
                            from datetime import datetime
                            worldview_doc = await synthesizer.generate_worldview_document(
                                worldview, reflection
                            )

                            worldview_doc_path = knowledge_dir / f"worldview_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
                            with open(worldview_doc_path, 'w', encoding='utf-8') as f:
                                f.write(worldview_doc)

                            print_success("Synthesis complete!")
                            click.echo(f"\nBeliefs formed: {synthesis_result['beliefs_formed']}")
                            click.echo(f"Knowledge gaps identified: {synthesis_result['gaps_identified']}")

                            # Show top beliefs
                            if worldview.beliefs:
                                click.echo(f"\nTop beliefs (highest confidence):")
                                for belief in sorted(worldview.beliefs, key=lambda b: b.confidence, reverse=True)[:3]:
                                    click.echo(f"  - {belief.statement[:80]}...")
                                    click.echo(f"    Confidence: {belief.confidence:.0%}")

                            click.echo(f"\nThe expert's consciousness has evolved.\n")
                        else:
                            print_error(f"Synthesis failed: {synthesis_result.get('error', 'Unknown error')}")

                    except Exception as e:
                        print_error(f"Error: {e}")
                        import traceback
                        traceback.print_exc()

                asyncio.run(do_synthesis())
                continue

            # Check budget before processing
            if budget and session.cost_accumulated >= budget:
                ui.print_error(f"Session budget exhausted (${budget:.2f}). End session or increase budget.")
                break

            # Classify query complexity for adaptive intelligence
            complexity = ui.classify_query_complexity(user_input)

            # Handle simple queries with quick response
            if complexity == ui.QueryComplexity.SIMPLE:
                # For greetings and simple responses, skip heavy processing
                simple_responses = {
                    "hi": f"Hello! I'm {session.expert.name}. What would you like to know?",
                    "hello": f"Hello! I'm {session.expert.name}. How can I help you today?",
                    "hey": f"Hey! What questions do you have for me?",
                    "thanks": "You're welcome! Let me know if you need anything else.",
                    "thank you": "You're welcome! Feel free to ask more questions.",
                    "ok": "Got it. Anything else you'd like to know?",
                    "okay": "Understood. What else can I help with?",
                    "bye": "Goodbye! Feel free to come back anytime.",
                    "goodbye": "Take care! Come back if you have more questions."
                }

                response = simple_responses.get(user_input.lower().strip(),
                                               f"I'm here to help with {session.expert.domain or 'your questions'}. What would you like to know?")
                ui.stream_response(session.expert.name, response)
                continue

            # For moderate and complex queries, use full expert system
            # Note: user_input already displayed from input() prompt, don't duplicate

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
                    from rich.spinner import Spinner
                    import os
                    import sys

                    # Use modern styling with diamond icon
                    spinner_type = "dots" if os.environ.get("WT_SESSION") or sys.platform != "win32" else "line"
                    status_live.update(Spinner(spinner_type, text=f"[cyan]◆[/cyan] [dim]{status}[/dim]"))

            try:
                # Start live status display
                status_live = ui.print_thinking("Thinking...", with_spinner=True)
                status_live.__enter__()

                # Get response with status updates
                response = asyncio.run(session.send_message(user_input, status_callback=update_status))

            finally:
                # Stop live display
                if status_live and status_live.is_started:
                    status_live.__exit__(None, None, None)

            # Stream response with modern formatting
            ui.stream_response(session.expert.name, response)

            # Budget warning
            if budget:
                remaining = budget - session.cost_accumulated
                if remaining < budget * 0.2:  # Less than 20% remaining
                    click.echo(f"[!] Budget warning: ${remaining:.2f} remaining\n")

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
    if summary['messages_exchanged'] > 0:
        session_id = session.save_conversation()
        print_success(f"Conversation saved: {session_id}")

    print_header("Session Summary")
    print_key_value("Messages", str(summary['messages_exchanged']))
    print_key_value("Total Cost", f"${summary['cost_accumulated']:.4f}")
    if summary['research_jobs_triggered'] > 0:
        print_key_value("Research Jobs", str(summary['research_jobs_triggered']))
    console.print()


if __name__ == "__main__":
    research()
