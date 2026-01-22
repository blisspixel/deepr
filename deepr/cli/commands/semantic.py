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

    # Validate budget/limit if provided
    if limit is not None:
        try:
            limit = validate_budget(limit, min_budget=0.1, max_budget=100.0)
        except click.UsageError as e:
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

        click.echo(f"\n{'='*70}")
        click.echo(f"  Strategic Company Research")
        click.echo(f"{'='*70}\n")

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
            click.echo(f"\n[ERROR] {result.get('error', 'Unknown error')}")
            return

        click.echo(f"\n{'='*70}")
        click.echo(f"  Company Research Complete")
        click.echo(f"{'='*70}\n")

        if result.get('job_id'):
            click.echo(f"Job ID: {result['job_id']}")
            click.echo(f"Scraped Content: {result['scraped_file']}")
            click.echo(f"Pages Captured: {result['pages_scraped']}")
        else:
            click.echo(f"Scraped Content: {result['scraped_file']}")
            click.echo(f"Pages Captured: {result['pages_scraped']}")

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
@click.option("--topics", type=int, default=5,
              help="Number of topics in learning curriculum (3-20, default: 5)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation for autonomous learning")
def make_expert(name: str, files: tuple, description: Optional[str], provider: str,
                learn: bool, budget: Optional[float], topics: int, yes: bool):
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

    # Validate budget if provided
    if budget is not None:
        try:
            budget = validate_budget(budget, min_budget=0.1, max_budget=100.0)
        except click.UsageError as e:
            click.echo(f"Error: {e}", err=True)
            return

    click.echo(f"\n{'='*70}")
    click.echo(f"  Creating Expert: {name}")
    click.echo(f"{'='*70}\n")

    if not files and not learn:
        click.echo("Error: No files specified. Use --files to add documents or --learn for autonomous learning.")
        click.echo("Example: deepr expert make 'My Expert' -f docs/*.md")
        click.echo("Or: deepr expert make 'My Expert' --learn --budget 10")
        return

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
            click.echo(f"Uploading {len(files)} file(s)...")
            for file_path in files:
                basename = os.path.basename(file_path)
                click.echo(f"  Uploading {basename}...")
                file_id = await provider_instance.upload_document(file_path)
                file_ids.append(file_id)
                click.echo(f"  [OK] {basename}")

        # Create vector store (empty if using --learn)
        click.echo(f"\nCreating knowledge base...")
        vector_store = await provider_instance.create_vector_store(
            name=f"expert-{name.lower().replace(' ', '-')}",
            file_ids=file_ids
        )

        # Wait for indexing only if there are files
        if files:
            click.echo(f"  Indexing files (this may take a minute)...")
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

    click.echo(f"\n[OK] Expert created successfully!")
    click.echo(f"\nExpert: {profile.name}")
    click.echo(f"Knowledge Base ID: {profile.vector_store_id}")
    click.echo(f"Documents: {profile.total_documents}")

    # Check if we should generate autonomous learning curriculum
    if learn:
        click.echo(f"\n{'='*70}")
        click.echo(f"  Autonomous Learning Mode")
        click.echo(f"{'='*70}\n")

        # Validate budget
        if not budget:
            click.echo("Error: --budget is required when using --learn")
            click.echo("Example: deepr expert make 'Expert' -f docs/*.md --learn --budget 10")
            return

        if budget <= 0:
            click.echo("Error: Budget must be positive")
            return

        # Generate curriculum
        async def generate_and_execute_curriculum():
            from deepr.experts.curriculum import CurriculumGenerator
            from deepr.experts.learner import AutonomousLearner
            from deepr.config import AppConfig

            config = AppConfig.from_env()

            # Show pre-generation cost estimate based on config defaults
            expert_config = config.expert
            deep_topics = min(5, topics)  # Max 5 deep research topics
            quick_topics = topics - deep_topics

            estimated_deep_cost = deep_topics * expert_config.deep_research_cost
            estimated_quick_cost = quick_topics * expert_config.quick_research_cost
            estimated_total_cost = estimated_deep_cost + estimated_quick_cost

            click.echo(f"\n{'='*70}")
            click.echo(f"  Cost Estimation (Before Curriculum Generation)")
            click.echo(f"{'='*70}\n")
            click.echo(f"Target topics: {topics}")
            click.echo(f"  - {deep_topics} deep research topics (campaign mode)")
            click.echo(f"  - {quick_topics} quick research topics (focus mode)")
            click.echo(f"\nEstimated cost breakdown:")
            click.echo(f"  - Deep research: {deep_topics} topics × ${expert_config.deep_research_cost:.2f} = ${estimated_deep_cost:.2f}")
            click.echo(f"  - Quick research: {quick_topics} topics × ${expert_config.quick_research_cost:.2f} = ${estimated_quick_cost:.2f}")
            click.echo(f"  - Total estimated: ${estimated_total_cost:.2f}")
            click.echo(f"  - Budget limit: ${budget:.2f}")

            if estimated_total_cost > budget:
                click.echo(f"\n[WARNING] Estimated cost (${estimated_total_cost:.2f}) exceeds budget (${budget:.2f})")
                click.echo(f"Curriculum will be automatically truncated to fit budget.")
            else:
                budget_remaining = budget - estimated_total_cost
                click.echo(f"\n[OK] Estimated cost fits within budget (${budget_remaining:.2f} margin)")

            click.echo(f"\nGenerating detailed curriculum with GPT-5...")

            generator = CurriculumGenerator(config)

            try:
                curriculum = await generator.generate_curriculum(
                    expert_name=name,
                    domain=description or name,
                    initial_documents=[os.path.basename(f) for f in files],
                    target_topics=topics,
                    budget_limit=budget
                )

                # Display curriculum for approval
                click.echo(f"\n{'='*70}")
                click.echo(f"  Learning Curriculum ({len(curriculum.topics)} topics)")
                click.echo(f"{'='*70}\n")

                for i, topic in enumerate(curriculum.topics, 1):
                    priority_marker = "*" * topic.priority
                    mode_indicator = "DEEP" if topic.research_mode == "campaign" else "quick"

                    # Map research type to emoji/indicator
                    type_indicators = {
                        "academic": "papers",
                        "technical-deep-dive": "arch",
                        "trends": "future",
                        "documentation": "docs",
                        "best-practices": "patterns"
                    }
                    type_indicator = type_indicators.get(topic.research_type, topic.research_type)

                    click.echo(f"{i}. {topic.title} [{mode_indicator}:{type_indicator}] [{priority_marker}]")
                    click.echo(f"   {topic.description}")
                    click.echo(f"   Mode: {topic.research_mode}, Type: {topic.research_type}, Est: ${topic.estimated_cost:.2f}, {topic.estimated_minutes}min")
                    if topic.dependencies:
                        click.echo(f"   Depends on: {', '.join(topic.dependencies)}")
                    click.echo()

                click.echo(f"\n{'='*70}")
                click.echo(f"  Final Cost Summary")
                click.echo(f"{'='*70}\n")
                click.echo(f"Actual estimated cost: ${curriculum.total_estimated_cost:.2f}")
                click.echo(f"Total estimated time: {curriculum.total_estimated_minutes} minutes ({curriculum.total_estimated_minutes/60:.1f} hours)")
                click.echo(f"Budget limit: ${budget:.2f}")

                if curriculum.total_estimated_cost > budget:
                    click.echo(f"\n[WARNING] Estimated cost exceeds budget!")
                    click.echo(f"  Curriculum has been truncated to fit budget")

                # Ask for confirmation only if --yes not provided AND budget not explicitly set
                # Rationale: If user set a budget and curriculum is within it, that's the safety mechanism
                click.echo(f"\n{'='*70}")
                needs_confirmation = not yes and budget is None
                if needs_confirmation and not click.confirm("Proceed with autonomous learning?", default=False):
                    click.echo("Learning cancelled.")
                    return None
                elif yes or budget is not None:
                    click.echo("Proceeding with autonomous learning...")
                    click.echo("(Budget protection active: execution will stop if limits exceeded)")

                # Execute curriculum
                click.echo(f"\n{'='*70}")
                click.echo(f"  Executing Autonomous Learning")
                click.echo(f"{'='*70}\n")

                learner = AutonomousLearner(config)

                progress = await learner.execute_curriculum(
                    expert=profile,
                    curriculum=curriculum,
                    budget_limit=budget,
                    dry_run=False
                )

                return progress

            except Exception as e:
                click.echo(f"\n[ERROR] Failed to generate curriculum: {e}")
                import traceback
                traceback.print_exc()
                return None

        progress = asyncio.run(generate_and_execute_curriculum())

        if progress:
            click.echo(f"\n{'='*70}")
            click.echo(f"  Learning Summary")
            click.echo(f"{'='*70}\n")
            click.echo(f"Completed: {len(progress.completed_topics)} topics")
            click.echo(f"Failed: {len(progress.failed_topics)} topics")
            click.echo(f"Success rate: {progress.success_rate()*100:.1f}%")
            click.echo(f"Total cost: ${progress.total_cost:.2f}")
            click.echo(f"Time elapsed: {(progress.completed_at - progress.started_at).total_seconds()/60:.1f} minutes")

    # Show usage
    click.echo(f"\nUsage:")
    click.echo(f'  deepr chat expert "{profile.name}"')
    click.echo(f'  deepr chat expert "{profile.name}" --agentic --budget 5')


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

    click.echo(f"\n{'='*70}")
    click.echo(f"  Domain Experts")
    click.echo(f"{'='*70}\n")

    store = ExpertStore()
    experts = store.list_all()

    if not experts:
        click.echo("No experts found.")
        click.echo("\nCreate one with:")
        click.echo('  deepr expert make "Expert Name" -f documents/*.md')
        return

    click.echo(f"Found {len(experts)} expert(s):\n")

    for expert in experts:
        click.echo(f"  {expert.name}")
        if expert.description:
            click.echo(f"    {expert.description}")
        click.echo(f"    Documents: {expert.total_documents}")
        click.echo(f"    Conversations: {expert.conversations}")
        if expert.research_triggered > 0:
            click.echo(f"    Research: {expert.research_triggered} jobs (${expert.total_research_cost:.2f})")

        # Show temporal information
        created_str = expert.created_at.strftime('%Y-%m-%d')
        updated_str = expert.updated_at.strftime('%Y-%m-%d')

        if created_str == updated_str:
            click.echo(f"    Created: {created_str}")
        else:
            click.echo(f"    Created: {created_str}, Updated: {updated_str}")

        # Show knowledge freshness status
        if expert.knowledge_cutoff_date:
            freshness = expert.get_freshness_status()
            age_days = freshness.get('age_days', 0)
            status = freshness.get('status', 'unknown')
            click.echo(f"    Knowledge: {age_days} days old [{status}]")

        click.echo()

    click.echo("Usage:")
    click.echo('  deepr chat expert "<name>"')


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

    click.echo(f"\n{'='*70}")
    click.echo(f"  Expert: {profile.name}")
    click.echo(f"{'='*70}\n")

    click.echo(f"Description: {profile.description or 'N/A'}")
    click.echo(f"Provider: {profile.provider}")
    click.echo(f"Model: {profile.model}")
    click.echo(f"\nKnowledge Base:")
    click.echo(f"  Vector Store ID: {profile.vector_store_id}")
    click.echo(f"  Documents: {profile.total_documents}")
    click.echo(f"  Source Files: {len(profile.source_files)}")

    if profile.source_files:
        click.echo("\n  Files:")
        for f in profile.source_files[:10]:
            click.echo(f"    - {os.path.basename(f)}")
        if len(profile.source_files) > 10:
            click.echo(f"    ... and {len(profile.source_files) - 10} more")

    click.echo(f"\nUsage Stats:")
    click.echo(f"  Conversations: {profile.conversations}")
    click.echo(f"  Research Triggered: {profile.research_triggered}")
    click.echo(f"  Total Research Cost: ${profile.total_research_cost:.2f}")

    if profile.research_jobs:
        click.echo(f"  Research Jobs: {len(profile.research_jobs)}")

    click.echo(f"\nCreated: {profile.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"Updated: {profile.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")


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
        click.echo(f"\n[OK] Expert deleted: {name}")
        click.echo(f"\nTo delete the knowledge base:")
        click.echo(f"  deepr brain delete {profile.vector_store_id}")
    else:
        click.echo(f"\nError: Failed to delete expert")


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

    click.echo(f"\n{'='*70}")
    click.echo(f"  Refreshing Expert Knowledge: {name}")
    click.echo(f"{'='*70}\n")

    async def do_refresh():
        store = ExpertStore()

        try:
            results = await store.refresh_expert_knowledge(name)

            click.echo(results["message"])
            click.echo()

            if results["uploaded"]:
                click.echo(f"[OK] Uploaded {len(results['uploaded'])} new documents:")
                for item in results["uploaded"]:
                    import os
                    basename = os.path.basename(item["path"])
                    click.echo(f"  - {basename}")
                    click.echo(f"    File ID: {item['file_id']}")
                click.echo()

            if results["failed"]:
                click.echo(f"[!] Failed to upload {len(results['failed'])} documents:")
                for item in results["failed"]:
                    import os
                    basename = os.path.basename(item["path"])
                    click.echo(f"  - {basename}: {item['error']}")
                click.echo()

            if not results["uploaded"] and not results["failed"]:
                click.echo("[OK] Expert knowledge is up to date")
                click.echo()

            # Show updated stats
            profile = store.load(name)
            if profile:
                click.echo(f"Expert now has {profile.total_documents} documents in knowledge base")
                click.echo(f"Last refreshed: {profile.last_knowledge_refresh.strftime('%Y-%m-%d %H:%M:%S')}")

            # Synthesize if requested
            if synthesize and (results["uploaded"] or yes or click.confirm("\nNo new documents. Synthesize existing knowledge anyway?")):
                click.echo(f"\n{'='*70}")
                click.echo(f"  Synthesizing Knowledge (Level 5 Consciousness)")
                click.echo(f"{'='*70}\n")
                click.echo("Expert is actively processing documents to form beliefs and meta-awareness...")
                click.echo("This may take 1-2 minutes...\n")

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
                        click.echo(f"[INFO] Loaded existing worldview ({existing_worldview.synthesis_count} prior syntheses)")
                    except Exception as e:
                        click.echo(f"[WARN] Could not load existing worldview: {e}")

                # Get documents to synthesize (uploaded or all if no new uploads)
                if results["uploaded"]:
                    docs_to_process = [{"path": item["path"]} for item in results["uploaded"]]
                else:
                    # Synthesize all documents
                    docs_dir = store.get_documents_dir(name)
                    all_docs = list(docs_dir.glob("*.md"))
                    docs_to_process = [{"path": str(f)} for f in all_docs[:10]]  # Limit to 10 for cost

                click.echo(f"Processing {len(docs_to_process)} documents...\n")

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

                    click.echo("[OK] Synthesis complete!")
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
                    click.echo(f"[X] Synthesis failed: {synthesis_result.get('error', 'Unknown error')}")

        except ValueError as e:
            click.echo(f"[X] Error: {e}")
        except Exception as e:
            click.echo(f"[X] Unexpected error: {e}")
            import traceback
            traceback.print_exc()

    from datetime import datetime
    asyncio.run(do_refresh())
    click.echo()


@expert.command(name="chat")
@click.argument("name")
@click.option("--budget", "-b", type=float, default=10.0,
              help="Session budget limit for research (default: $10)")
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
    from datetime import datetime

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
                    documents=session.expert.total_documents
                )
                continue

            elif user_input == "/clear":
                session.messages = []
                ui.console.print("\n[green][OK][/green] Conversation history cleared\n")
                continue

            elif user_input == "/trace":
                ui.print_trace(session.reasoning_trace)
                continue

            elif user_input.startswith("/learn "):
                # Extract file path
                file_path = user_input[7:].strip()
                if not file_path:
                    click.echo("\n[X] Usage: /learn <file_path>\n")
                    continue

                from pathlib import Path
                from deepr.experts.profile import ExpertStore
                import shutil

                path = Path(file_path)
                if not path.exists():
                    click.echo(f"\n[X] File not found: {file_path}\n")
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
                            click.echo(f"[OK] Document uploaded to knowledge base")
                            click.echo(f"    Expert now has {session.expert.total_documents + 1} documents")
                            click.echo(f"\nTip: Use /synthesize to help the expert form beliefs from this knowledge\n")

                            # Reload expert to get updated document count
                            session.expert = store.load(session.expert.name)
                        elif results["failed"]:
                            click.echo(f"[X] Failed to upload: {results['failed'][0]['error']}\n")
                        else:
                            click.echo(f"[INFO] Document already in knowledge base\n")
                    except Exception as e:
                        click.echo(f"[X] Error: {e}\n")

                asyncio.run(upload_document())
                continue

            elif user_input == "/synthesize":
                click.echo(f"\n{'='*70}")
                click.echo(f"  Synthesizing Consciousness")
                click.echo(f"{'='*70}\n")
                click.echo("[INFO] Expert is actively processing knowledge to form beliefs...")
                click.echo("This may take 1-2 minutes...\n")

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
                                click.echo(f"[INFO] Building on {existing_worldview.synthesis_count} prior syntheses")
                            except Exception as e:
                                click.echo(f"[WARN] Could not load existing worldview: {e}")

                        # Get recent documents (last 10)
                        docs_dir = store.get_documents_dir(session.expert.name)
                        all_docs = sorted(docs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
                        docs_to_process = [{"path": str(f)} for f in all_docs[:10]]

                        click.echo(f"Processing {len(docs_to_process)} recent documents...\n")

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

                            click.echo("[OK] Synthesis complete!")
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
                            click.echo(f"[X] Synthesis failed: {synthesis_result.get('error', 'Unknown error')}\n")

                    except Exception as e:
                        click.echo(f"[X] Error: {e}\n")
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
            click.echo(f"\n[X] Error: {e}\n")
            continue

    # Final summary
    summary = session.get_session_summary()

    # Save conversation before ending
    if summary['messages_exchanged'] > 0:
        session_id = session.save_conversation()
        click.echo(f"\n[OK] Conversation saved: {session_id}")
    click.echo(f"\n{'='*70}")
    click.echo(f"Session Summary:")
    click.echo(f"  Messages: {summary['messages_exchanged']}")
    click.echo(f"  Total Cost: ${summary['cost_accumulated']:.4f}")
    if summary['research_jobs_triggered'] > 0:
        click.echo(f"  Research Jobs: {summary['research_jobs_triggered']}")
    click.echo(f"{'='*70}\n")


if __name__ == "__main__":
    research()
