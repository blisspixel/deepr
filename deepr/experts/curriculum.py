"""Self-directed learning curriculum generation for domain experts.

This module enables experts to autonomously generate comprehensive learning plans
based on their domain and initial knowledge base.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import click
import httpx
from openai import AsyncOpenAI

from deepr.config import AppConfig

logger = logging.getLogger(__name__)


class CurriculumGenerationProgress:
    """Track and display curriculum generation progress.

    This class provides real-time feedback during curriculum generation,
    showing users what's happening at each step and how long operations take.

    Attributes:
        callback: Optional callback function for custom progress handling
        start_time: Timestamp when current step started
        current_step: Name of the current step being executed
    """

    def __init__(self, callback: Optional[Callable[[str], None]] = None):
        """Initialize progress tracker.

        Args:
            callback: Optional function to call with progress messages.
                     If None, messages are printed to console via click.echo.
        """
        self.callback = callback
        self.start_time = None
        self.current_step = None

    def start(self, step: str):
        """Start a new step in the curriculum generation process.

        Args:
            step: Name/description of the step being started
        """
        self.current_step = step
        self.start_time = datetime.now()
        self._notify(f"{step}")

    def update(self, message: str):
        """Update progress within the current step.

        Args:
            message: Progress update message
        """
        self._notify(f"  {message}")

    def complete(self, message: str = "Complete"):
        """Mark the current step as complete.

        Args:
            message: Completion message (default: "Complete")
        """
        from deepr.cli.colors import get_symbol

        symbol = get_symbol("success")

        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            self._notify(f"  {symbol} {message} ({elapsed:.1f}s)")
        else:
            self._notify(f"  {symbol} {message}")

    def error(self, message: str):
        """Report an error in the current step.

        Args:
            message: Error message
        """
        from deepr.cli.colors import get_symbol

        symbol = get_symbol("error")
        self._notify(f"  {symbol} {message}")

    def _notify(self, message: str):
        """Send notification to callback or print to console.

        Args:
            message: Message to display
        """
        if self.callback:
            self.callback(message)
        else:
            click.echo(message)

    def _timestamp(self) -> str:
        """Get current timestamp in HH:MM:SS format.

        Returns:
            Formatted timestamp string
        """
        return datetime.now().strftime("%H:%M:%S")


@dataclass
class SourceReference:
    """A specific source to learn from."""

    url: Optional[str] = None  # URL to fetch/scrape
    title: Optional[str] = None  # Title of the source
    source_type: str = "unknown"  # "documentation", "paper", "guide", "blog", "video"
    description: Optional[str] = None  # What this source contains

    def __post_init__(self):
        if self.url and not self.title:
            # Extract title from URL if not provided
            self.title = self.url.split("/")[-1] or self.url


@dataclass
class LearningTopic:
    """A single topic in the learning curriculum."""

    title: str
    description: str
    research_mode: str  # "campaign" for deep research, "focus" for quick lookup
    research_type: str  # "academic", "documentation", "best-practices", "trends", "technical-deep-dive"
    estimated_cost: float
    estimated_minutes: int
    priority: int  # 1 (highest) to 5 (lowest)
    research_prompt: str
    dependencies: list[str] = None  # Topic titles this depends on
    sources: list[SourceReference] = None  # Specific sources to learn from (populated in discovery phase)

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.sources is None:
            self.sources = []


@dataclass
class LearningCurriculum:
    """Complete learning curriculum for an expert."""

    expert_name: str
    domain: str
    topics: list[LearningTopic]
    total_estimated_cost: float
    total_estimated_minutes: int
    generated_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "expert_name": self.expert_name,
            "domain": self.domain,
            "topics": [
                {
                    "title": t.title,
                    "description": t.description,
                    "research_mode": t.research_mode,
                    "research_type": t.research_type,
                    "estimated_cost": t.estimated_cost,
                    "estimated_minutes": t.estimated_minutes,
                    "priority": t.priority,
                    "research_prompt": t.research_prompt,
                    "dependencies": t.dependencies,
                    "sources": [
                        {"url": s.url, "title": s.title, "source_type": s.source_type, "description": s.description}
                        for s in t.sources
                    ]
                    if t.sources
                    else [],
                }
                for t in self.topics
            ],
            "total_estimated_cost": self.total_estimated_cost,
            "total_estimated_minutes": self.total_estimated_minutes,
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LearningCurriculum":
        """Create from dictionary."""
        return cls(
            expert_name=data["expert_name"],
            domain=data["domain"],
            topics=[
                LearningTopic(
                    title=t["title"],
                    description=t["description"],
                    research_mode=t.get("research_mode", "focus"),  # Default to focus if not specified
                    research_type=t.get("research_type", "best-practices"),  # Default type
                    estimated_cost=t["estimated_cost"],
                    estimated_minutes=t["estimated_minutes"],
                    priority=t["priority"],
                    research_prompt=t["research_prompt"],
                    dependencies=t.get("dependencies", []),
                    sources=[
                        SourceReference(
                            url=s.get("url"),
                            title=s.get("title"),
                            source_type=s.get("source_type", "unknown"),
                            description=s.get("description"),
                        )
                        for s in t.get("sources", [])
                    ],
                )
                for t in data["topics"]
            ],
            total_estimated_cost=data["total_estimated_cost"],
            total_estimated_minutes=data["total_estimated_minutes"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
        )


class CurriculumGenerator:
    """Generates comprehensive learning curricula for domain experts."""

    def __init__(self, config: AppConfig):
        self.config = config

    async def generate_curriculum(
        self,
        expert_name: str,
        domain: str,
        initial_documents: list[str],
        target_topics: int = 15,
        budget_limit: Optional[float] = None,
        timeout: int = 120,
        enable_discovery: bool = True,
        docs_count: Optional[int] = None,
        quick_count: Optional[int] = None,
        deep_count: Optional[int] = None,
    ) -> LearningCurriculum:
        """Generate a learning curriculum for an expert using two-phase approach.

        Phase 1 (Discovery): Ask LLM what sources exist (docs, papers, guides)
        Phase 2 (Synthesis): Create curriculum that fetches and learns from those sources

        Args:
            expert_name: Name of the expert
            domain: Domain description
            initial_documents: List of initial document filenames/paths
            target_topics: Target number of topics (10-20)
            budget_limit: Optional budget constraint
            timeout: Timeout in seconds for API calls (default: 120)
                    Can be configured via DEEPR_CURRICULUM_TIMEOUT env var
            enable_discovery: If True, run discovery phase to identify sources first
            docs_count: Optional exact number of documentation topics (FOCUS mode)
            quick_count: Optional exact number of quick research topics (FOCUS mode)
            deep_count: Optional exact number of deep research topics (CAMPAIGN mode)

        Returns:
            LearningCurriculum with topics ordered by priority and dependencies
        """
        # Check for environment variable override
        timeout = int(os.getenv("DEEPR_CURRICULUM_TIMEOUT", str(timeout)) or str(timeout))

        # Create progress tracker
        progress = CurriculumGenerationProgress()

        # Show what we're generating
        if docs_count or quick_count or deep_count:
            total = (docs_count or 0) + (quick_count or 0) + (deep_count or 0)
            parts = []
            if docs_count:
                parts.append(f"{docs_count} documentation")
            if quick_count:
                parts.append(f"{quick_count} quick research")
            if deep_count:
                parts.append(f"{deep_count} deep research")
            topic_desc = " + ".join(parts)
            progress._notify(f"Generating curriculum ({total} topics: {topic_desc})...")
        else:
            progress._notify(f"Generating curriculum ({target_topics} topics)...")

        # PHASE 1: Discovery - What sources exist?
        discovered_sources = []
        if enable_discovery:
            progress.start("Discovering sources...")
            discovered_sources = await self._discover_sources(domain=domain, timeout=timeout, progress=progress)
            if discovered_sources:
                progress.complete(f"Found {len(discovered_sources)}")
            else:
                progress.complete("None found")

        # PHASE 2: Synthesis - Build curriculum that learns from sources
        progress.start("Building curriculum...")

        # Build the curriculum generation prompt (now includes discovered sources and topic counts)
        prompt = self._build_curriculum_prompt(
            expert_name,
            domain,
            initial_documents,
            target_topics,
            budget_limit,
            discovered_sources=discovered_sources,
            docs_count=docs_count,
            quick_count=quick_count,
            deep_count=deep_count,
        )

        # Call GPT-5 with retry logic and timeout enforcement
        response = await self._call_gpt5_with_retry(prompt=prompt, max_retries=3, timeout=timeout, progress=progress)

        # Parse the structured response
        curriculum = self._parse_curriculum_response(response, expert_name, domain)

        # Validate exact topic counts if specified
        if docs_count is not None or quick_count is not None or deep_count is not None:
            # Count actual topics by type
            actual_docs = sum(1 for t in curriculum.topics if t.research_type == "documentation")
            actual_quick = sum(1 for t in curriculum.topics if t.research_type in ["best-practices", "trends"])
            actual_deep = sum(1 for t in curriculum.topics if t.research_type in ["academic", "technical-deep-dive"])

            expected_docs = docs_count or 0
            expected_quick = quick_count or 0
            expected_deep = deep_count or 0

            # If counts don't match, take the first N of each type
            if actual_docs != expected_docs or actual_quick != expected_quick or actual_deep != expected_deep:
                filtered_topics = []

                # Take exactly the requested number of each type
                docs_taken = 0
                quick_taken = 0
                deep_taken = 0

                for topic in curriculum.topics:
                    if topic.research_type == "documentation" and docs_taken < expected_docs:
                        filtered_topics.append(topic)
                        docs_taken += 1
                    elif topic.research_type in ["best-practices", "trends"] and quick_taken < expected_quick:
                        filtered_topics.append(topic)
                        quick_taken += 1
                    elif topic.research_type in ["academic", "technical-deep-dive"] and deep_taken < expected_deep:
                        filtered_topics.append(topic)
                        deep_taken += 1

                # If we didn't get enough topics, that's an error
                if len(filtered_topics) < (expected_docs + expected_quick + expected_deep):
                    logger.warning(
                        "Only got %d topics, expected %d",
                        len(filtered_topics),
                        expected_docs + expected_quick + expected_deep,
                    )
                    logger.warning("  Got: docs=%d, quick=%d, deep=%d", docs_taken, quick_taken, deep_taken)

                # Update curriculum with filtered topics
                curriculum.topics = filtered_topics
                curriculum.total_estimated_cost = sum(t.estimated_cost for t in filtered_topics)
                curriculum.total_estimated_minutes = sum(t.estimated_minutes for t in filtered_topics)

        # Validate budget constraints
        if budget_limit and curriculum.total_estimated_cost > budget_limit:
            # Truncate to fit budget
            curriculum = self._truncate_to_budget(curriculum, budget_limit)

        return curriculum

    async def _call_gpt5_with_retry(
        self,
        prompt: str,
        max_retries: int = 3,
        timeout: int = 120,
        progress: Optional[CurriculumGenerationProgress] = None,
    ) -> str:
        """Call GPT-5 Chat Completions API with retry logic and timeout enforcement.

        Uses the synchronous Chat Completions API (not Responses API) because
        curriculum generation should complete in seconds, not minutes.

        Args:
            prompt: The curriculum generation prompt
            max_retries: Maximum number of retry attempts (default: 3)
            timeout: Timeout in seconds for HTTP request (default: 120)
                    This is the HTTP timeout, not job execution time.
                    Chat completions typically return in 10-60 seconds.
            progress: Optional progress tracker for user feedback

        Returns:
            The GPT-5 response text

        Raises:
            APITimeoutError: If the HTTP request times out
            APIRateLimitError: If rate limit is exceeded after all retries
            APIServerError: If server error persists after all retries
            CurriculumGenerationError: For other API errors
        """
        import asyncio

        import openai

        from deepr.experts.errors import (
            APIRateLimitError,
            APIServerError,
            APITimeoutError,
            CurriculumGenerationError,
            NetworkError,
        )

        last_error = None

        for attempt in range(max_retries):
            try:
                if progress:
                    if attempt > 0:
                        progress.update(f"Retrying... (attempt {attempt + 1}/{max_retries})")

                # Get API key
                if isinstance(self.config, dict):
                    api_key = self.config.get("api_key") or self.config.get("openai_api_key")
                else:
                    api_key = self.config.provider.openai_api_key

                # Create client with timeout
                client = AsyncOpenAI(api_key=api_key, timeout=httpx.Timeout(timeout, connect=10.0))

                try:
                    # Make API call using Chat Completions (synchronous, not Responses API)
                    # This returns immediately instead of submitting an async job
                    # Use the model registry to get the best model for curriculum generation
                    from deepr.providers.registry import get_models_by_specialization

                    # Get best curriculum planning model (fast, good at structured output)
                    curriculum_models = get_models_by_specialization("curriculum")
                    if not curriculum_models:
                        # Fallback to reasoning models if no curriculum-specific model
                        curriculum_models = get_models_by_specialization("reasoning")

                    # Use the cheapest curriculum model (sorted by cost)
                    model_name = curriculum_models[0].model if curriculum_models else "gpt-5.2"

                    response_obj = await client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert curriculum designer. Generate structured learning plans quickly and accurately.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.7,  # Some creativity for topic generation
                        response_format={"type": "json_object"},  # Ensure JSON output
                    )

                    # Extract response from chat completion
                    response = response_obj.choices[0].message.content or ""

                    if progress:
                        progress.complete("Done")

                    return response
                finally:
                    # Always close the client to prevent event loop errors
                    await client.close()

            except httpx.TimeoutException:
                last_error = APITimeoutError(timeout)
                if progress:
                    progress.error(f"Request timed out after {timeout}s")
                # Don't retry timeouts - they're unlikely to succeed
                break

            except openai.RateLimitError as e:
                retry_after = getattr(e, "retry_after", None)
                last_error = APIRateLimitError(retry_after)
                if progress:
                    progress.error("Rate limit exceeded")

                if attempt < max_retries - 1:
                    # Exponential backoff: 2s, 4s, 8s
                    delay = 2 ** (attempt + 1)
                    if progress:
                        progress.update(f"Waiting {delay}s before retry...")
                    await asyncio.sleep(delay)
                    continue
                break

            except openai.APIStatusError as e:
                if 500 <= e.status_code < 600:
                    # Server error - retry
                    last_error = APIServerError(e.status_code, str(e))
                    if progress:
                        progress.error(f"OpenAI server error (code {e.status_code})")

                    if attempt < max_retries - 1:
                        delay = 2 ** (attempt + 1)
                        if progress:
                            progress.update(f"Waiting {delay}s before retry...")
                        await asyncio.sleep(delay)
                        continue
                else:
                    # Client error - don't retry
                    last_error = CurriculumGenerationError(f"API error {e.status_code}: {e}")
                    break

            except (httpx.ConnectError, httpx.NetworkError):
                last_error = NetworkError()
                if progress:
                    progress.error("Network connection failed")
                # Don't retry network errors
                break

            except Exception as e:
                last_error = CurriculumGenerationError(f"Unexpected error: {e}")
                if progress:
                    progress.error(str(e))
                break

        # All retries exhausted or non-retryable error
        if progress and last_error:
            progress.error(f"Failed after {attempt + 1} attempt(s)")
        raise last_error

    async def _discover_sources(
        self,
        domain: str,
        timeout: int = 120,  # 2 minutes is plenty for a chat completion
        progress: Optional[CurriculumGenerationProgress] = None,
    ) -> list[SourceReference]:
        """Phase 1: Discover what sources exist for this domain.

        This asks the LLM: "What documentation, research papers, and knowledge sources
        exist for [domain] that would make a great expert?"

        Uses Chat Completions API (synchronous) which returns in 10-60 seconds typically.

        Args:
            domain: The domain to discover sources for
            timeout: HTTP timeout for API call (default: 120s)
                    Can be overridden with DEEPR_DISCOVERY_TIMEOUT env var
            progress: Optional progress tracker

        Returns:
            List of SourceReference objects with URLs, titles, and types
        """
        # Check for environment variable override
        timeout = int(os.getenv("DEEPR_DISCOVERY_TIMEOUT", str(timeout)) or str(timeout))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        discovery_prompt = f"""You are a research librarian helping to identify the best sources for building domain expertise.

DOMAIN: {domain}
TODAY'S DATE: {today}

OBJECTIVE:
Identify specific, high-quality sources that exist RIGHT NOW that would help build comprehensive expertise in this domain.

THINK LIKE A LIBRARIAN:
- What are the OFFICIAL documentation sites? (vendor docs, API references)
- What are the KEY research papers? (academic papers with citations)
- What are the AUTHORITATIVE guides? (tutorials, best practices)
- What are the INDUSTRY reports? (whitepapers, case studies)
- What are the COMPARISON resources? (vs alternatives, trade-offs)

CRITICAL REQUIREMENTS:
1. **Provide REAL URLs** - These must be actual, fetchable URLs (not examples)
2. **Prioritize official sources** - Vendor docs, academic papers, industry standards
3. **Include variety** - Mix of documentation, research, guides, comparisons
4. **Current sources** - Prefer sources from {today.split("-")[0]} or recent years
5. **Specific, not generic** - "NVIDIA Omniverse USD Guide" not "USD documentation"

SOURCE CATEGORIES (aim for mix):
- **documentation** (30-40%): Official vendor docs, API references, SDKs
- **paper** (20-30%): Academic papers, research publications
- **guide** (20-30%): Tutorials, getting started guides, best practices
- **blog** (10-20%): Technical blogs, case studies, real-world examples
- **video** (optional): Conference talks, tutorial series

OUTPUT FORMAT (JSON):
{{
  "sources": [
    {{
      "url": "https://docs.nvidia.com/omniverse/latest/index.html",
      "title": "NVIDIA Omniverse Official Documentation",
      "source_type": "documentation",
      "description": "Complete official documentation for Omniverse platform including USD, Kit SDK, Connectors"
    }},
    {{
      "url": "https://arxiv.org/abs/2301.12345",
      "title": "Digital Twin Architecture Patterns for Industrial IoT",
      "source_type": "paper",
      "description": "Academic paper on digital twin architectural patterns and real-time synchronization"
    }}
  ]
}}

IMPORTANT GUIDELINES:
- Aim for 10-20 sources total
- Each URL must be real and fetchable (check that it exists)
- Prioritize sources that are:
  * Official (vendor documentation)
  * Authoritative (academic papers, industry standards)
  * Current (from {today.split("-")[0]} or recent years)
  * Comprehensive (covers multiple aspects)
- Include a mix of source types (not all documentation, not all papers)
- For papers, prefer arxiv.org, ACM, IEEE, or conference proceedings
- For documentation, prefer official vendor sites
- For guides, prefer official tutorials or well-known technical blogs

EXAMPLE - Microsoft Azure AI Expert:
- documentation: https://learn.microsoft.com/azure/ai-services/
- documentation: https://learn.microsoft.com/azure/ai-studio/
- paper: https://arxiv.org/abs/2401.xxxxx (RAG architecture patterns)
- guide: https://github.com/Azure-Samples/azure-ai-studio-samples
- blog: https://techcommunity.microsoft.com/azure-ai/

Generate the source list now for: {domain}"""

        if progress:
            progress.update("Identifying sources...")

        try:
            # Call GPT-5 to discover sources
            response = await self._call_gpt5_with_retry(
                prompt=discovery_prompt, max_retries=3, timeout=timeout, progress=progress
            )
        except Exception as e:
            # If discovery fails, log warning and return empty list
            # Curriculum generation will proceed without discovered sources
            if progress:
                progress.error(f"Discovery failed: {e!s}")
            return []

        # Parse response
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(json_str)
            sources = []

            for source_data in data.get("sources", []):
                sources.append(
                    SourceReference(
                        url=source_data.get("url"),
                        title=source_data.get("title"),
                        source_type=source_data.get("source_type", "unknown"),
                        description=source_data.get("description"),
                    )
                )

            if progress:
                # Show breakdown by type
                type_counts = {}
                for s in sources:
                    type_counts[s.source_type] = type_counts.get(s.source_type, 0) + 1
                breakdown = ", ".join(f"{count} {type_}" for type_, count in sorted(type_counts.items()))
                progress.update(f"{breakdown}")

            return sources

        except json.JSONDecodeError as e:
            if progress:
                progress.error(f"Parse failed: {e}")
            # Return empty list - curriculum generation will proceed without discovered sources
            return []

    def _build_curriculum_prompt(
        self,
        expert_name: str,
        domain: str,
        initial_documents: list[str],
        target_topics: int,
        budget_limit: Optional[float],
        discovered_sources: Optional[list[SourceReference]] = None,
        docs_count: Optional[int] = None,
        quick_count: Optional[int] = None,
        deep_count: Optional[int] = None,
    ) -> str:
        """Build the curriculum generation prompt.

        Args:
            discovered_sources: Optional list of sources from discovery phase
            docs_count: Optional exact number of documentation topics to generate
            quick_count: Optional exact number of quick research topics to generate
            deep_count: Optional exact number of deep research topics to generate
        """

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        doc_list = "\n".join(f"- {doc}" for doc in initial_documents)

        # Get actual cost values from config
        if isinstance(self.config, dict):
            quick_cost = self.config.get("expert", {}).get("quick_research_cost", 0.002)
            deep_cost = self.config.get("expert", {}).get("deep_research_cost", 1.0)
        else:
            quick_cost = self.config.expert.quick_research_cost
            deep_cost = self.config.expert.deep_research_cost

        # Format discovered sources if available
        sources_section = ""
        if discovered_sources:
            sources_section = f"""
DISCOVERED SOURCES (Phase 1 Discovery):
We've identified {len(discovered_sources)} high-quality sources for this domain:

"""
            # Group by type
            by_type = {}
            for source in discovered_sources:
                if source.source_type not in by_type:
                    by_type[source.source_type] = []
                by_type[source.source_type].append(source)

            for source_type, sources in sorted(by_type.items()):
                sources_section += f"\n**{source_type.upper()} ({len(sources)} sources):**\n"
                for source in sources:
                    sources_section += f"- {source.title}\n"
                    sources_section += f"  URL: {source.url}\n"
                    if source.description:
                        sources_section += f"  Description: {source.description}\n"

            sources_section += """
IMPORTANT: When creating topics, you should:
1. **Reference these sources** - Include URLs in research prompts where relevant
2. **Synthesize understanding** - Topics should help expert form viewpoint from these sources
3. **Fetch and learn** - Research should fetch these sources and extract key insights
4. **Build expertise** - Expert should develop beliefs/understanding, not just store documents

Example topic using discovered sources:
{
  "title": "NVIDIA Omniverse USD Format Deep Dive",
  "description": "Master USD format by studying official docs and academic papers on scene description",
  "research_mode": "campaign",
  "research_type": "documentation",
  "research_prompt": "Study NVIDIA Omniverse USD documentation at docs.nvidia.com/omniverse and USD format papers. Extract: composition arcs, layer system, performance patterns, vs glTF/FBX trade-offs.",
  "sources": [
    {"url": "https://docs.nvidia.com/omniverse/usd/latest/", "title": "USD Official Docs", "source_type": "documentation"},
    {"url": "https://arxiv.org/abs/xxxx", "title": "USD Format Analysis", "source_type": "paper"}
  ]
}
"""

        budget_guidance = ""

        # Check if user specified exact topic counts
        has_explicit_counts = any([docs_count is not None, quick_count is not None, deep_count is not None])

        if has_explicit_counts:
            # User specified exact counts - provide guidance for those specific counts
            docs_count = docs_count or 0
            quick_count = quick_count or 0
            deep_count = deep_count or 0

            total_topics = docs_count + quick_count + deep_count
            estimated_cost = (docs_count * quick_cost) + (quick_count * quick_cost) + (deep_count * deep_cost)

            budget_guidance = f"""
EXPLICIT TOPIC COUNTS (User-Specified):
The user has requested EXACTLY:
- {docs_count} documentation topics (FOCUS mode, ~${quick_cost:.3f} each)
- {quick_count} quick research topics (FOCUS mode, ~${quick_cost:.3f} each)
- {deep_count} deep research topics (CAMPAIGN mode, ~${deep_cost:.2f} each)
- Total: {total_topics} topics
- Estimated cost: ${estimated_cost:.2f}

CRITICAL REQUIREMENTS:
1. You MUST generate EXACTLY {docs_count} documentation topics
2. You MUST generate EXACTLY {quick_count} quick research topics (best-practices, trends, comparisons)
3. You MUST generate EXACTLY {deep_count} deep research topics (academic, technical-deep-dive)
4. Total topics MUST be exactly {total_topics}

TOPIC TYPE DEFINITIONS:
- **DOCUMENTATION** (research_type: "documentation", research_mode: "focus")
  * Official vendor docs, API references, SDKs
  * Latest features, product guides
  * "What exists NOW" questions

- **QUICK RESEARCH** (research_type: "best-practices" or "trends", research_mode: "focus")
  * Comparisons, trade-offs, when to use what
  * Industry trends, emerging patterns
  * Real-world case studies

- **DEEP RESEARCH** (research_type: "academic" or "technical-deep-dive", research_mode: "campaign")
  * Theoretical foundations, research papers
  * Architectural patterns, WHY questions
  * Complex analysis requiring extended reasoning

EXAMPLE OUTPUT for --docs 1 --quick 1 --deep 1:
{{
  "topics": [
    {{
      "title": "FastAPI Official Documentation 2026",
      "description": "Survey FastAPI docs: routing, dependencies, async, testing",
      "research_mode": "focus",
      "research_type": "documentation",
      "estimated_cost": {quick_cost},
      "estimated_minutes": 10,
      "priority": 2,
      "research_prompt": "Document FastAPI 2026: routing, dependencies, async patterns, testing. List key APIs."
    }},
    {{
      "title": "FastAPI vs Flask vs Django: decision framework",
      "description": "Compare frameworks for API development trade-offs",
      "research_mode": "focus",
      "research_type": "best-practices",
      "estimated_cost": {quick_cost},
      "estimated_minutes": 10,
      "priority": 3,
      "research_prompt": "Compare FastAPI, Flask, Django for APIs: performance, features, use cases, when to use each."
    }},
    {{
      "title": "ASGI architecture and async patterns",
      "description": "Deep dive into ASGI design and async request handling",
      "research_mode": "campaign",
      "research_type": "technical-deep-dive",
      "estimated_cost": {deep_cost},
      "estimated_minutes": 45,
      "priority": 1,
      "research_prompt": "Analyze ASGI architecture: event loop, async/await, concurrency models. Compare to WSGI."
    }}
  ]
}}

Generate EXACTLY {total_topics} topics with the specified breakdown.
"""
        elif budget_limit:
            # Smart allocation based on budget
            # For a proper expert, we need: 40% docs, 30% research, 30% quick
            # Campaign (deep): uses deep_cost
            # Focus (quick): uses quick_cost

            # Calculate optimal mix within budget
            # Start with minimum viable: 2 campaign topics for depth
            min_campaign = 2
            campaign_cost = min_campaign * deep_cost

            # Use remaining budget for focus topics
            remaining_budget = budget_limit - campaign_cost
            max_focus = int(remaining_budget / quick_cost)

            # Adjust if we can't afford minimum
            if remaining_budget < 0:
                min_campaign = int(budget_limit / deep_cost)
                max_focus = 0
                campaign_cost = min_campaign * deep_cost
                remaining_budget = budget_limit - campaign_cost

            # Calculate actual allocation
            campaign_topics = min(min_campaign, target_topics, int(budget_limit / deep_cost))
            focus_topics = min(max_focus, target_topics - campaign_topics)

            # Ensure we don't exceed target
            total_topics = campaign_topics + focus_topics
            if total_topics > target_topics:
                focus_topics = target_topics - campaign_topics

            estimated_cost = (campaign_topics * deep_cost) + (focus_topics * quick_cost)

            budget_guidance = f"""
BUDGET CONSTRAINT: ${budget_limit:.2f}
TARGET TOPICS: {target_topics}

SMART ALLOCATION (optimized for budget and quality):
- {campaign_topics} CAMPAIGN topics (deep research): ${campaign_topics * deep_cost:.2f}
- {focus_topics} FOCUS topics (documentation + quick research): ${focus_topics * quick_cost:.2f}
- Total estimated: ${estimated_cost:.2f}

AVAILABLE MODELS:

1. **CAMPAIGN** (o4-mini-deep-research): ${deep_cost:.2f}, 30-45 min
   - Extended reasoning + web browsing
   - Use for: WHY questions, architectural reasoning, foundational principles
   - Best for: Core concepts that require deep understanding

2. **FOCUS** (grok-4-fast): ${quick_cost:.3f}, 5-10 min
   - Web search + structured thinking
   - Use for: Documentation, current state, comparisons, trends
   - Best for: What exists NOW, official docs, quick lookups

CONTENT MIX REQUIREMENTS (CRITICAL):
You MUST ensure the curriculum has:
- At least 30% documentation topics (research_type: "documentation")
- At least 30% research topics (research_type: "academic" or "technical-deep-dive")
- Mix of both CAMPAIGN and FOCUS modes

ALLOCATION STRATEGY:

**DOCUMENTATION** (~40% = {int(total_topics * 0.40)} topics) - FOCUS
- Official vendor documentation: FOCUS ($0.25)
- API references and SDKs: FOCUS ($0.25)
- Product guides and tutorials: FOCUS ($0.25)
- Latest features and releases: FOCUS ($0.25)
Purpose: Ensure expert knows official sources and current capabilities

**FOUNDATIONAL RESEARCH** (~30% = {int(total_topics * 0.30)} topics) - CAMPAIGN
- Core architectural patterns: CAMPAIGN ($2.00)
- Theoretical foundations: CAMPAIGN ($2.00)
- Design principles and trade-offs: CAMPAIGN ($2.00)
Purpose: Deep understanding of WHY things work

**QUICK RESEARCH** (~30% = {int(total_topics * 0.30)} topics) - FOCUS
- Trends and evolution: FOCUS ($0.25)
- Comparisons and alternatives: FOCUS ($0.25)
- Best practices and patterns: FOCUS ($0.25)
Purpose: Practical knowledge and context

KEY INSIGHT:
- Use CAMPAIGN for deep "WHY" questions (2-3 topics max)
- Use FOCUS for documentation and "WHAT" questions (majority of topics)
- This gives you {total_topics} topics within ${budget_limit:.2f} budget
- More topics = better expert, even if most are quick FOCUS lookups
"""

        return f"""You are designing a self-directed learning curriculum for a domain expert.

EXPERT PROFILE:
- Name: {expert_name}
- Domain: {domain}
- Initial Knowledge Base:
{doc_list}

{sources_section}

OBJECTIVE:
Generate a comprehensive learning curriculum of {target_topics} research topics that will transform this expert from having basic document knowledge to deep domain expertise.

TODAY'S DATE: {today}

DOMAIN CONTEXT:
Analyze the domain "{domain}" to determine if it's:
- CURRENT/EVOLVING: Modern technology, active products, ongoing development (e.g., "Azure AI", "React", "Kubernetes")
- HISTORICAL/ESTABLISHED: Historical topics, vintage items, established practices (e.g., "1930s cameras", "Roman architecture", "Classical music")

For CURRENT domains, focus on: latest developments, current state, emerging trends, what's new in {today.split("-")[0]}
For HISTORICAL domains, focus on: historical context, evolution, key periods, influential examples, preservation

CRITICAL - BUILD A TRUE EXPERT (Not Just Documentation Reader!):

A real expert needs comprehensive knowledge. Adapt these dimensions to the domain:

**DIMENSION 1: CORE KNOWLEDGE (30% of topics)**
Purpose: Essential understanding of the domain
- For CURRENT domains: What exists NOW, latest features, current best practices in {today.split("-")[0]}
- For HISTORICAL domains: Key periods, major developments, defining characteristics, notable examples
- Foundational concepts everyone should know
- Primary sources and authoritative references

**DIMENSION 2: FOUNDATIONAL DEPTH (25% of topics)**
Purpose: Deep understanding of principles
- Why things work the way they do (not just HOW, but WHY)
- Theoretical foundations and core concepts
- Design principles and patterns
- Technical or artistic fundamentals
- Use "academic" or "technical-deep-dive" research types

**DIMENSION 3: HISTORICAL CONTEXT (15% of topics)**
Purpose: Evolution and development over time
- For CURRENT domains: How the domain evolved to its current state
- For HISTORICAL domains: Timeline of developments, key innovations
- Key innovations and breakthroughs
- Influential figures or organizations
- What problems led to current solutions
- Lessons learned from the past

**DIMENSION 4: COMPARATIVE WISDOM (20% of topics)**
Purpose: Make good decisions through analysis
- Compare different approaches, models, or examples
- Trade-offs and decision criteria
- When to use X vs Y
- Real-world case studies
- Common pitfalls and best practices

**DIMENSION 5: CONTEXT & CONNECTIONS (10% of topics)**
Purpose: Broader understanding
- For CURRENT domains: Future trends, emerging patterns, what's coming in {today.split("-")[0]}-{int(today.split("-")[0]) + 1}
- For HISTORICAL domains: Cultural context, influence on later developments, relevance today
- Connections to related domains
- Practical applications
- Industry direction and momentum

WHY THIS STRUCTURE:
An expert who only knows latest docs is shallow and unhelpful. They need:
- Current state: So they know what exists NOW (Agent 365, latest features)
- Foundational depth: So they understand WHY (not just copy-paste docs)
- Historical context: So they learn from past failures
- Comparative wisdom: So they make good trade-off decisions
- Future vision: So they prepare for what's next

CURRICULUM REQUIREMENTS:

1. **Topics 1-3 (30%): CURRENT STATE**
   - #1: What's new (MANDATORY FIRST TOPIC)
   - #2-3: Deep dives on major recent products

2. **Topics 4-5 (25%): FOUNDATIONAL DEPTH**
   - Timeless principles, architecture patterns, theory
   - Use "academic" or "technical-deep-dive" types

3. **Topic 6 (15%): HISTORICAL CONTEXT**
   - Evolution of domain, lessons learned, why we're here

4. **Topics 7-8 (20%): COMPARATIVE WISDOM**
   - Trade-offs, when to use what, case studies, pitfalls

5. **Topic 9-10 (10%): FUTURE VISION**
   - Emerging trends, 2026-2027 direction

THINK HOLISTICALLY:
- An expert needs to understand systems from multiple angles
- Different contexts require different knowledge (e.g., Python vs Node.js patterns)
- Security, cost, and compliance cut across all layers
- Real-world solutions combine multiple services/patterns

{budget_guidance}

TOPIC STRUCTURE:
For each topic, provide:
- title: Clear, specific topic name
- description: 1-2 sentences explaining what will be learned
- research_mode: "campaign" for deep research topics (5 max), "focus" for quick lookups (rest)
- research_type: One of:
  * "academic" - Research papers, theoretical foundations
  * "technical-deep-dive" - Architectural patterns, algorithms
  * "trends" - Market analysis, future directions
  * "documentation" - Latest APIs, SDKs, tools, services
  * "best-practices" - Real-world implementation patterns
- estimated_cost: $1.50-2.50 for campaign, $0.15-0.30 for focus
- estimated_minutes: 30-60 for campaign, 8-15 for focus
- priority: 1 (critical foundation) to 5 (nice-to-have)
- research_prompt: The exact prompt to use for research
  * CRITICAL: Must be under 300 characters (hard limit for API)
  * Be concise but specific
  * Include year {today.split("-")[0]} for currency
  * **Include URLs from discovered sources when relevant**
  * Example: "Study NVIDIA Omniverse docs at docs.nvidia.com/omniverse. Extract: USD format, Kit SDK, Connectors, RTX rendering. Synthesize understanding of platform architecture."
- dependencies: List of topic titles that should be researched first
- sources: List of source references from discovered sources (if applicable)
  * Include URL, title, and source_type for each
  * These will be fetched and used during research
  * Expert will synthesize understanding from these sources

OUTPUT FORMAT (JSON):
{{
  "topics": [
    {{
      "title": "Topic name",
      "description": "What will be learned",
      "research_mode": "campaign",
      "research_type": "academic",
      "estimated_cost": 2.00,
      "estimated_minutes": 45,
      "priority": 1,
      "research_prompt": "Research prompt with year {today.split("-")[0]} and URLs",
      "dependencies": [],
      "sources": [
        {{
          "url": "https://example.com/doc",
          "title": "Source Title",
          "source_type": "documentation"
        }}
      ]
    }}
  ]
}}

IMPORTANT GUIDELINES:
- **CRITICAL: You MUST create a MIX of content types:**
  * At least 30% must be "documentation" type (official docs, APIs, guides)
  * At least 30% must be "academic" or "technical-deep-dive" type (research depth)
  * Remaining can be "best-practices" or "trends"
- **CRITICAL: You MUST use BOTH campaign and focus modes:**
  * Use "campaign" for 2-3 deep research topics (WHY questions, foundations)
  * Use "focus" for majority of topics (documentation, comparisons, trends)
- Each research prompt should be specific and actionable
- For "documentation" type: Include specific service/tool names and year {today.split("-")[0]}
- For "academic" type: Request research papers, citations, and theoretical foundations
- For "best-practices" type: Request case studies, patterns, and proven approaches
- Estimated costs:
  - Campaign: ${deep_cost:.2f} (multi-phase deep research)
  - Focus: ${quick_cost:.3f} (single-phase targeted lookup)
- Total topics: exactly {target_topics}
- Priority 1-2 for campaign topics (foundations)
- Priority 3-5 for focus topics (supplementary)
- Dependencies create logical learning flow

EXAMPLE - NVIDIA Omniverse Expert (5 topics with $10 budget):

**DOCUMENTATION** (Topics 1-2, 40%) - FOCUS
#1: "NVIDIA Omniverse official documentation 2026" (FOCUS, documentation, priority 2, $0.25)
    "Survey NVIDIA Omniverse 2026 official docs: USD, Connectors, Kit SDK, Nucleus, RTX rendering. List key APIs and capabilities."

#2: "Omniverse Digital Twin APIs and SDKs" (FOCUS, documentation, priority 2, $0.25)
    "Document Omniverse Digital Twin APIs: IoT integration, real-time sync, physics simulation, data streaming. Include code examples."

**FOUNDATIONAL RESEARCH** (Topics 3-4, 40%) - CAMPAIGN
#3: "Digital twin architecture patterns and trade-offs" (CAMPAIGN, technical-deep-dive, priority 1, $2.00)
    "Analyze digital twin architectures: real-time vs batch, edge vs cloud, physics fidelity trade-offs. Compare approaches with examples."

#4: "USD format and 3D data interchange theory" (CAMPAIGN, academic, priority 1, $2.00)
    "Research Universal Scene Description: format design, composition arcs, layer system, performance. Compare to glTF, FBX alternatives."

**QUICK RESEARCH** (Topic 5, 20%) - FOCUS
#5: "Omniverse vs Unity vs Unreal for digital twins" (FOCUS, best-practices, priority 3, $0.25)
    "Compare Omniverse, Unity, Unreal for industrial digital twins: features, performance, cost, use cases. Real-world examples."

Total: 2 CAMPAIGN ($4.00) + 3 FOCUS ($0.75) = $4.75 within $10 budget
Content mix: 40% documentation, 40% research, 20% quick = BALANCED ✓
    "Compare Azure AI Foundry and AI Studio in 2026: features, use cases, migration path, when to use which, pricing differences."

**FOUNDATIONAL DEPTH (Topics 4-5):**
#4: "RAG architecture patterns: naive to agentic" (CAMPAIGN, technical-deep-dive, priority 1)
    "Compare RAG approaches: naive retrieval, hybrid search, re-ranking, agentic retrieval. Trade-offs, when to use each, implementation patterns."

#5: "LLM security fundamentals: injection to data leakage" (CAMPAIGN, academic, priority 2)
    "LLM security threats: prompt injection, data leakage, model theft, jailbreaking. Mitigations, defense patterns, Purview integration."

**HISTORICAL CONTEXT (Topic 6):**
#6: "Evolution of Microsoft AI: LUIS to GPT-5" (FOCUS, trends, priority 3)
    "Microsoft AI evolution 2018-2026: LUIS, Bot Framework, Cognitive Services, OpenAI partnership, Copilot, Agent 365. Why each shift happened."

**COMPARATIVE WISDOM (Topics 7-8):**
#7: "OpenAI vs Azure OpenAI vs M365 Copilot: decision framework" (FOCUS, best-practices, priority 2)
    "When to use OpenAI API vs Azure OpenAI vs M365 Copilot: cost, governance, features, integration. Real-world case studies."

#8: "Common AI implementation pitfalls in enterprise" (FOCUS, best-practices, priority 3)
    "Top failures in enterprise AI: context window misuse, cost overruns, poor prompt design, security gaps. How to avoid each."

**FUTURE VISION (Topics 9-10):**
#9: "Agentic AI trends: 2026-2027 direction" (FOCUS, trends, priority 3)
    "Emerging patterns in agentic AI: multi-agent systems, tool orchestration, autonomous planning. What's coming in next 12 months."

#10: "Microsoft AI roadmap signals: Ignite 2025 analysis" (FOCUS, trends, priority 4)
    "Read between the lines of Ignite 2025: what Microsoft is betting on, deprecation signals, strategic direction."

This creates an expert who:
- Knows Agent 365 and latest products (Current State)
- Understands WHY RAG patterns exist (Foundational Depth)
- Knows how we got from LUIS to today (Historical Context)
- Can make OpenAI vs Azure decisions (Comparative Wisdom)
- Anticipates what's coming next (Future Vision)

Generate the curriculum now:"""

    def _parse_curriculum_response(self, response: str, expert_name: str, domain: str) -> LearningCurriculum:
        """Parse the GPT response into a LearningCurriculum."""

        # Extract JSON from response (handle markdown code blocks)
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse curriculum JSON: {e}\n{json_str}") from e

        # Create LearningTopic objects
        topics = []
        for topic_data in data["topics"]:
            # Parse sources if present
            sources = []
            if topic_data.get("sources"):
                for source_data in topic_data["sources"]:
                    sources.append(
                        SourceReference(
                            url=source_data.get("url"),
                            title=source_data.get("title"),
                            source_type=source_data.get("source_type", "unknown"),
                            description=source_data.get("description"),
                        )
                    )

            topics.append(
                LearningTopic(
                    title=topic_data["title"],
                    description=topic_data["description"],
                    research_mode=topic_data.get("research_mode", "focus"),
                    research_type=topic_data.get("research_type", "best-practices"),
                    estimated_cost=topic_data["estimated_cost"],
                    estimated_minutes=topic_data["estimated_minutes"],
                    priority=topic_data["priority"],
                    research_prompt=topic_data["research_prompt"],
                    dependencies=topic_data.get("dependencies", []),
                    sources=sources,
                )
            )

        # Calculate totals
        total_cost = sum(t.estimated_cost for t in topics)
        total_minutes = sum(t.estimated_minutes for t in topics)

        return LearningCurriculum(
            expert_name=expert_name,
            domain=domain,
            topics=topics,
            total_estimated_cost=total_cost,
            total_estimated_minutes=total_minutes,
            generated_at=datetime.now(timezone.utc),
        )

    def _truncate_to_budget(self, curriculum: LearningCurriculum, budget_limit: float) -> LearningCurriculum:
        """Truncate curriculum to fit within budget while preserving priorities."""

        # Sort by priority (1 = highest), then by cost
        sorted_topics = sorted(curriculum.topics, key=lambda t: (t.priority, t.estimated_cost))

        # Keep adding topics until we hit budget
        selected_topics = []
        running_cost = 0.0

        for topic in sorted_topics:
            if running_cost + topic.estimated_cost <= budget_limit:
                selected_topics.append(topic)
                running_cost += topic.estimated_cost
            else:
                # Check if we can fit any remaining priority 1-2 topics
                if topic.priority <= 2 and running_cost + topic.estimated_cost <= budget_limit * 1.1:
                    # Allow 10% overage for critical topics
                    selected_topics.append(topic)
                    running_cost += topic.estimated_cost

        # Recalculate totals
        total_cost = sum(t.estimated_cost for t in selected_topics)
        total_minutes = sum(t.estimated_minutes for t in selected_topics)

        return LearningCurriculum(
            expert_name=curriculum.expert_name,
            domain=curriculum.domain,
            topics=selected_topics,
            total_estimated_cost=total_cost,
            total_estimated_minutes=total_minutes,
            generated_at=curriculum.generated_at,
        )

    def get_execution_order(self, curriculum: LearningCurriculum) -> list[list[LearningTopic]]:
        """Get topics organized into execution phases based on dependencies.

        Returns:
            List of phases, where each phase is a list of topics that can be
            researched in parallel (no dependencies on each other).
        """
        phases = []
        completed = set()
        remaining = list(curriculum.topics)

        while remaining:
            # Find topics with no unmet dependencies
            ready = []
            for topic in remaining:
                deps_met = all(dep in completed for dep in topic.dependencies)
                if deps_met:
                    ready.append(topic)

            if not ready:
                # Circular dependency or error - just take everything remaining
                phases.append(remaining)
                break

            # This phase can run in parallel
            phases.append(ready)

            # Mark as completed
            for topic in ready:
                completed.add(topic.title)
                remaining.remove(topic)

        return phases
