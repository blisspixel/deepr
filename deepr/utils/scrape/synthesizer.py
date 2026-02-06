"""Content synthesis from scraped data."""

import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


class ContentSynthesizer:
    """Synthesizes scraped content into structured insights."""

    def __init__(self, llm_client=None):
        """
        Initialize synthesizer.

        Args:
            llm_client: LLM client for synthesis (optional, will import if needed)
        """
        self.llm_client = llm_client

    def synthesize(
        self,
        company_name: str,
        base_url: str,
        scraped_data: Dict[str, str],
        purpose: str = "company research",
    ) -> Dict[str, any]:
        """
        Synthesize scraped content into structured insights.

        Args:
            company_name: Target company name
            base_url: Base URL that was scraped
            scraped_data: Dict of {url: content}
            purpose: Purpose of scraping (company research, documentation, etc.)

        Returns:
            Dict with synthesized insights
        """
        if not scraped_data:
            logger.warning("No scraped data to synthesize")
            return {
                "success": False,
                "error": "No content to synthesize",
            }

        logger.info(f"Synthesizing {len(scraped_data)} pages for {company_name}")

        # Combine all content
        combined_content = self._combine_content(scraped_data)

        # Truncate if too long (for LLM context limits)
        max_chars = 100000  # Adjust based on LLM limits
        if len(combined_content) > max_chars:
            logger.warning(f"Content too long ({len(combined_content)} chars), truncating to {max_chars}")
            combined_content = combined_content[:max_chars] + "\n\n[Content truncated due to length]"

        # Generate synthesis prompt based on purpose
        prompt = self._create_synthesis_prompt(
            company_name=company_name,
            base_url=base_url,
            content=combined_content,
            purpose=purpose,
        )

        # Get LLM synthesis
        try:
            insights = self._get_llm_synthesis(prompt)
        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}")
            return {
                "success": False,
                "error": f"Synthesis failed: {e}",
            }

        return {
            "success": True,
            "company_name": company_name,
            "base_url": base_url,
            "pages_scraped": len(scraped_data),
            "insights": insights,
            "scraped_urls": list(scraped_data.keys()),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _combine_content(self, scraped_data: Dict[str, str]) -> str:
        """
        Combine scraped content with source attribution.

        Args:
            scraped_data: Dict of {url: content}

        Returns:
            Combined content string
        """
        combined = []

        for url, content in scraped_data.items():
            combined.append(f"Source: {url}\n")
            combined.append(content)
            combined.append("\n" + "=" * 80 + "\n")

        return "\n".join(combined)

    def _create_synthesis_prompt(
        self,
        company_name: str,
        base_url: str,
        content: str,
        purpose: str,
    ) -> str:
        """
        Create synthesis prompt based on purpose.

        Args:
            company_name: Company name
            base_url: Base URL
            content: Combined content
            purpose: Research purpose

        Returns:
            Prompt string
        """
        if purpose == "company research":
            return self._company_research_prompt(company_name, base_url, content)
        elif purpose == "documentation":
            return self._documentation_prompt(company_name, base_url, content)
        elif purpose == "competitive intel":
            return self._competitive_intel_prompt(company_name, base_url, content)
        else:
            return self._generic_prompt(company_name, base_url, content)

    def _company_research_prompt(self, company_name: str, base_url: str, content: str) -> str:
        """Generate company research synthesis prompt."""
        return f"""Analyze this content from {company_name}'s website ({base_url}).

Extract and synthesize structured information about the company:

1. COMPANY OVERVIEW
   - What does this company do? (core business)
   - Industry and market focus
   - Company size and stage (if mentioned)

2. PRODUCTS/SERVICES
   - Main offerings (detailed list)
   - Key features and capabilities
   - Target use cases

3. VALUE PROPOSITION
   - How do they position themselves?
   - What makes them unique/different?
   - Key benefits they emphasize

4. TARGET AUDIENCE
   - Who are their customers?
   - Industries/sectors they serve
   - User personas mentioned

5. KEY MESSAGING
   - Main themes in their communication
   - How they describe their solution
   - Problem they claim to solve

6. COMPANY INFORMATION
   - Leadership/team (if mentioned)
   - Funding/investors (if mentioned)
   - Locations/offices (if mentioned)
   - Recent news or announcements

7. PRICING/BUSINESS MODEL
   - Pricing information (if available)
   - Business model (SaaS, consulting, product, etc.)
   - Free trial or demo availability

Format as markdown with clear sections. Include specific quotes when relevant.
Cite which pages information came from.

Content to analyze:

{content}

Synthesized Analysis:"""

    def _documentation_prompt(self, company_name: str, base_url: str, content: str) -> str:
        """Generate documentation synthesis prompt."""
        return f"""Analyze this documentation from {base_url}.

Extract and organize:

1. MAIN TOPICS COVERED
   - What are the primary documentation sections?
   - What functionality is documented?

2. KEY CONCEPTS
   - Important terms and definitions
   - Core concepts explained
   - Architecture or design patterns

3. GETTING STARTED
   - Installation or setup steps
   - Prerequisites
   - Quick start guides

4. API/INTERFACE REFERENCE
   - Available APIs, methods, or commands
   - Parameters and options
   - Return values or outputs

5. EXAMPLES AND USE CASES
   - Code examples provided
   - Common use cases
   - Best practices mentioned

6. VERSION INFORMATION
   - Current version (if mentioned)
   - Compatibility notes
   - Deprecations or changes

Format as structured markdown. Maintain technical accuracy.

Content:

{content}

Documentation Summary:"""

    def _competitive_intel_prompt(self, company_name: str, base_url: str, content: str) -> str:
        """Generate competitive intelligence synthesis prompt."""
        return f"""Analyze {company_name}'s website for competitive intelligence purposes.

Focus on:

1. COMPETITIVE POSITIONING
   - How do they position vs alternatives?
   - Competitive advantages claimed
   - Market differentiators

2. PRODUCT CAPABILITIES
   - Feature set and functionality
   - Technology stack (if mentioned)
   - Integrations and partnerships

3. PRICING STRATEGY
   - Pricing model and tiers
   - Value for money positioning
   - Enterprise vs SMB focus

4. MARKETING MESSAGES
   - Key value propositions
   - Target pain points
   - Customer testimonials/case studies

5. COMPANY MOMENTUM
   - Recent product launches
   - News and announcements
   - Growth indicators

6. CUSTOMER BASE
   - Notable customers (if listed)
   - Industries served
   - Use case examples

Be objective. Focus on factual information from their website.

Content:

{content}

Competitive Analysis:"""

    def _generic_prompt(self, company_name: str, base_url: str, content: str) -> str:
        """Generate generic synthesis prompt."""
        return f"""Analyze and summarize the key information from {base_url}.

Provide a structured summary covering:
- Main topics and themes
- Key information and facts
- Important details and insights
- How the information is organized

Content:

{content}

Summary:"""

    def _get_llm_synthesis(self, prompt: str) -> str:
        """
        Get LLM synthesis of content.

        Args:
            prompt: Synthesis prompt

        Returns:
            LLM response
        """
        if not self.llm_client:
            # LLM client not configured - raise silently
            raise AttributeError("No LLM client configured")

        # Use provided LLM client
        return self.llm_client(prompt)


class ProvenanceTracker:
    """Tracks which URLs contributed which information."""

    def __init__(self):
        self.citations: Dict[str, List[str]] = {}

    def add_citation(self, fact: str, source_url: str):
        """
        Record that a fact came from a source.

        Args:
            fact: The factual claim
            source_url: URL it came from
        """
        if fact not in self.citations:
            self.citations[fact] = []
        if source_url not in self.citations[fact]:
            self.citations[fact].append(source_url)

    def get_sources(self, fact: str) -> List[str]:
        """
        Get sources for a fact.

        Args:
            fact: The factual claim

        Returns:
            List of source URLs
        """
        return self.citations.get(fact, [])

    def format_citation(self, fact: str) -> str:
        """
        Format a fact with its citations.

        Args:
            fact: The factual claim

        Returns:
            Formatted string with citations
        """
        sources = self.get_sources(fact)
        if not sources:
            return fact

        citations = ", ".join(f"[{i + 1}]" for i in range(len(sources)))
        return f"{fact} {citations}"
