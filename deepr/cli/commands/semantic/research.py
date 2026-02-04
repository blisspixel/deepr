"""Research, learn, team, and check commands."""

import click
import asyncio
from typing import Optional
from deepr.cli.commands.run import _run_single, _run_campaign, _run_team, TraceFlags
from deepr.cli.colors import print_header, print_error, print_key_value, console
from deepr.cli.output import OutputContext, OutputMode, output_options


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
@click.option("--explain", is_flag=True, help="Show decision reasoning after completion")
@click.option("--timeline", is_flag=True, help="Show phase timeline after completion")
@click.option("--full-trace", is_flag=True, help="Export full trace to data/traces/")
@click.option("--no-fallback", is_flag=True, help="Disable automatic provider fallback on failure")
@output_options
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
    explain: bool,
    timeline: bool,
    full_trace: bool,
    no_fallback: bool,
    output_context: OutputContext,
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

    # Track whether user explicitly specified a provider (before defaults are applied)
    user_specified_provider = provider is not None

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
        if output_context.mode == OutputMode.VERBOSE:
            click.echo(f"[Using {provider} provider (default for {operation_type})]")

    if model is None:
        if is_deep_research:
            model = os.getenv("DEEPR_DEEP_RESEARCH_MODEL", "o3-deep-research")
        else:
            model = os.getenv("DEEPR_DEFAULT_MODEL", "grok-4-fast")
        if output_context.mode == OutputMode.VERBOSE:
            click.echo(f"[Using {model} model (default for {provider})]")

    # Handle scraping if requested
    if scrape:
        if output_context.mode == OutputMode.VERBOSE:
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
                if output_context.mode == OutputMode.VERBOSE:
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
                if output_context.mode == OutputMode.VERBOSE:
                    click.echo(f"[Scraped content saved and added to research context]\n")
            else:
                if output_context.mode == OutputMode.VERBOSE:
                    click.echo(f"[WARNING: Scraping failed - continuing with web research only]")
                    click.echo(f"[Error: {results.get('error', 'Unknown error')}]\n")

        except Exception as e:
            if output_context.mode == OutputMode.VERBOSE:
                click.echo(f"[WARNING: Scraping failed - {e}]")
                click.echo(f"[Continuing with web research only]\n")

    # Auto-detect mode if set to auto
    if mode == "auto":
        detected_mode = detect_research_mode(query)
        if output_context.mode == OutputMode.VERBOSE:
            click.echo(f"[Auto-detected mode: {detected_mode}]")
    else:
        detected_mode = mode

    # Modify query for docs mode to optimize for documentation
    if detected_mode == "docs":
        if not query.lower().startswith("create") and not query.lower().startswith("document"):
            query = f"Create comprehensive documentation for: {query}"

    # Call the underlying _run_single implementation
    trace_flags = TraceFlags(explain=explain, timeline=timeline, full_trace=full_trace)
    asyncio.run(_run_single(
        query, model, provider, no_web, no_code, upload, limit, yes,
        output_context, trace_flags=trace_flags,
        no_fallback=no_fallback,
        user_specified_provider=user_specified_provider,
    ))


@click.command()
@click.argument("topic")
@click.option("--model", "-m", default="o3-deep-research", help="Research model (default: o3-deep-research for comprehensive results)")
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
@click.option("--model", "-m", default="o3-deep-research", help="Research model (default: o3-deep-research for comprehensive results)")
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


@click.command()
@click.argument("claim")
@click.option("--sources", "-s", help="Restrict verification to specific domains/sources")
@click.option("--provider", "-p", help="Provider (default: xai for fast verification)")
@click.option("--model", "-m", help="Model (default: grok-4-fast)")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed reasoning")
def check(claim: str, sources: Optional[str], provider: Optional[str],
          model: Optional[str], verbose: bool):
    """Verify a factual claim quickly.

    Uses a cost-effective model to verify facts and return a structured
    verdict with confidence level and supporting evidence.

    Examples:
        deepr check "Does Fabric support private endpoints?"
        deepr check "GPT-5 was released in 2025" --sources official
        deepr check "Python 3.12 added pattern matching" -v
    """
    from deepr.cli.validation import validate_prompt

    # Validate claim
    try:
        claim = validate_prompt(claim, max_length=5000, field_name="claim")
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    asyncio.run(_verify_fact(claim, sources, provider, model, verbose))


async def _verify_fact(
    claim: str,
    sources: Optional[str],
    provider: Optional[str],
    model: Optional[str],
    verbose: bool
):
    """Verify a fact with schema validation and structured output."""
    import json
    import re
    from pydantic import BaseModel, Field, field_validator
    from typing import List
    from deepr.config import AppConfig
    from deepr.providers import create_provider
    from deepr.core.evidence import Evidence, FactCheckResult, Verdict
    from deepr.cli.progress import ProgressFeedback

    # Pydantic model for LLM response validation
    class FactCheckResponse(BaseModel):
        verdict: str = Field(..., pattern="^(TRUE|FALSE|UNCERTAIN)$")
        confidence: float = Field(..., ge=0.0, le=1.0)
        scope: str = Field(default="general")
        evidence: List[dict] = Field(default_factory=list)
        reasoning: str = ""

        @field_validator('confidence', mode='before')
        @classmethod
        def normalize_confidence(cls, v):
            if isinstance(v, str):
                v = float(v.rstrip('%')) / 100 if '%' in v else float(v)
            return max(0.0, min(1.0, v))

    config = AppConfig.from_env()
    progress = ProgressFeedback()

    # Get provider and model for fact checking
    if not provider or not model:
        task_provider, task_model = config.provider.get_model_for_task("fact_check")
        provider = provider or task_provider
        model = model or task_model

    console.print(f"[dim]Using {provider}/{model} for verification[/dim]")

    # Get API key based on provider
    if provider == "xai":
        import os
        api_key = os.getenv("XAI_API_KEY")
    elif provider == "openai":
        api_key = config.provider.openai_api_key
    elif provider == "gemini":
        import os
        api_key = os.getenv("GEMINI_API_KEY")
    else:
        api_key = config.provider.openai_api_key

    provider_instance = create_provider(provider, api_key=api_key)

    # Build verification prompt
    scope_instruction = f"\nScope: Only check against {sources}" if sources else ""

    prompt = f'''Verify this claim and respond with valid JSON only.

Claim: {claim}{scope_instruction}

Required JSON format:
{{
    "verdict": "TRUE" | "FALSE" | "UNCERTAIN",
    "confidence": 0.0-1.0,
    "scope": "what sources/domain was checked",
    "evidence": [
        {{"source": "source name", "quote": "relevant quote", "supports_claim": true/false}}
    ],
    "reasoning": "brief explanation of verdict"
}}

Rules:
- TRUE: Claim is supported by evidence
- FALSE: Claim is contradicted by evidence
- UNCERTAIN: Insufficient or conflicting evidence
- Confidence should reflect certainty (0.5 = uncertain, 0.9+ = very confident)
'''

    # Execute with retry loop
    max_attempts = 3
    last_error = None
    result = None

    with progress.operation("Verifying claim..."):
        for attempt in range(max_attempts):
            try:
                response = await provider_instance.complete(prompt, model=model)
                content = response.choices[0].message.content

                # Extract JSON from response
                json_match = re.search(r'\{[\s\S]*\}', content)
                if not json_match:
                    raise ValueError("No JSON found in response")

                data = json.loads(json_match.group())
                validated = FactCheckResponse(**data)

                # Convert to canonical result
                evidence_list = [
                    Evidence.create(
                        source=e.get("source", "unknown"),
                        quote=e.get("quote", ""),
                        supports=[claim] if e.get("supports_claim") else [],
                        contradicts=[claim] if not e.get("supports_claim") else []
                    )
                    for e in validated.evidence
                ]

                result = FactCheckResult(
                    claim=claim,
                    verdict=Verdict(validated.verdict),
                    confidence=validated.confidence,
                    scope=validated.scope,
                    evidence=evidence_list,
                    reasoning=validated.reasoning,
                    cost=getattr(response, 'cost', 0.0) if hasattr(response, 'cost') else 0.0
                )
                break

            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                if attempt < max_attempts - 1:
                    prompt += f"\n\nPrevious response was invalid: {e}. Please provide valid JSON."

    # Handle failure
    if result is None:
        result = FactCheckResult(
            claim=claim,
            verdict=Verdict.UNCERTAIN,
            confidence=0.0,
            scope="verification_failed",
            evidence=[],
            reasoning=f"Schema validation failed after {max_attempts} attempts: {last_error}"
        )
        progress.phase_error("Verification failed")
    else:
        progress.phase_complete("Verification complete", cost=result.cost)

    # Display result
    console.print()
    console.print(result.to_cli_output())

    if verbose and result.reasoning:
        console.print(f"\n[dim]Full reasoning: {result.reasoning}[/dim]")
