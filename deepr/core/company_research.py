"""Strategic Company Research Orchestrator.

This module orchestrates the two-phase company research workflow:
1. Web Scraping: Capture fresh company website content
2. Deep Research: Strategic analysis with scraped content as context

The output is a consultant-grade strategic overview suitable for M&A, competitive
intelligence, strategic planning, and due diligence.
"""

import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Optional

from deepr.config import load_config
from deepr.core.research import ResearchOrchestrator
from deepr.utils.scrape import ScrapeConfig, scrape_for_company_research

logger = logging.getLogger(__name__)


class CompanyResearchOrchestrator:
    """Orchestrates strategic company research workflow."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """Initialize the orchestrator.

        Args:
            config: Optional configuration dict. If None, loads from environment.
        """
        self.config = config or load_config()
        self.research_orchestrator = ResearchOrchestrator(self.config)

    async def research_company(
        self,
        company_name: str,
        website: str,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        budget_limit: Optional[float] = None,
        skip_confirmation: bool = False,
        scrape_only: bool = False,
    ) -> dict[str, Any]:
        """Execute strategic company research.

        Args:
            company_name: Official company name
            website: Company website URL
            model: Research model (default: o4-mini-deep-research)
            provider: AI provider (default: openai)
            budget_limit: Cost limit in dollars
            skip_confirmation: Skip budget confirmation
            scrape_only: Only run scraping phase (for testing)

        Returns:
            Dict containing:
                - job_id: Research job ID (if research submitted)
                - scraped_file: Path to scraped content
                - pages_scraped: Number of pages scraped
                - status: Current status
                - message: Status message
        """
        # Phase 1: Web Scraping
        logger.info("=" * 70)
        logger.info("  Phase 1: Web Scraping")
        logger.info("=" * 70)
        logger.info("Company: %s", company_name)
        logger.info("Website: %s", website)
        logger.info("Scraping company website for fresh content...")

        # Configure scraping for company research
        scrape_config = ScrapeConfig(
            max_pages=25,  # More pages for comprehensive company research
            max_depth=3,  # Deeper crawl to get product/services pages
            try_selenium=True,  # Use Selenium for dynamic content
            try_pdf=True,  # Capture PDF documents (annual reports, etc.)
        )

        # Execute scraping
        scrape_results = await self._scrape_company_website(
            company_url=website, company_name=company_name, config=scrape_config
        )

        if not scrape_results["success"]:
            return {
                "success": False,
                "error": f"Scraping failed: {scrape_results.get('error', 'Unknown error')}",
                "message": "Could not scrape company website. Try again or check URL.",
            }

        logger.info("Scraped %d pages successfully", scrape_results["pages_scraped"])
        logger.info("Content saved to: %s", scrape_results["scraped_file"])

        # If scrape-only mode, return here
        if scrape_only:
            return {
                "success": True,
                "scraped_file": scrape_results["scraped_file"],
                "pages_scraped": scrape_results["pages_scraped"],
                "status": "scrape_complete",
                "message": f"Scraping complete. {scrape_results['pages_scraped']} pages captured.",
            }

        # Phase 2: Deep Research
        logger.info("=" * 70)
        logger.info("  Phase 2: Strategic Research")
        logger.info("=" * 70)
        logger.info("Submitting deep research job with scraped content...")

        # Build strategic research prompt
        research_prompt = self._build_research_prompt(company_name, website)

        # Use defaults if not specified
        model = model or os.getenv("DEEPR_DEEP_RESEARCH_MODEL", "o4-mini-deep-research")
        provider = provider or os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")

        logger.info("Model: %s", model)
        logger.info("Provider: %s", provider)

        # Submit research job with scraped content as uploaded document
        job_result = await self.research_orchestrator.submit_research(
            prompt=research_prompt,
            model=model,
            provider=provider,
            uploaded_files=[scrape_results["scraped_file"]],
            budget_limit=budget_limit,
            skip_confirmation=skip_confirmation,
        )

        if not job_result.get("success"):
            return {
                "success": False,
                "error": job_result.get("error", "Research submission failed"),
                "scraped_file": scrape_results["scraped_file"],
                "pages_scraped": scrape_results["pages_scraped"],
            }

        job_id = job_result["job_id"]

        logger.info("Research job submitted: %s", job_id)
        logger.info("This will take 5-20 minutes depending on model and depth.")
        logger.info("Monitor progress:")
        logger.info("  deepr jobs status %s", job_id)
        logger.info("Retrieve results:")
        logger.info("  deepr jobs get %s", job_id)

        return {
            "success": True,
            "job_id": job_id,
            "scraped_file": scrape_results["scraped_file"],
            "pages_scraped": scrape_results["pages_scraped"],
            "status": "research_submitted",
            "message": f"Research job submitted: {job_id}. Check status with 'deepr jobs status {job_id}'",
        }

    async def _scrape_company_website(
        self, company_url: str, company_name: str, config: ScrapeConfig
    ) -> dict[str, Any]:
        """Scrape company website and save to temporary file.

        Args:
            company_url: Company website URL
            company_name: Company name
            config: Scrape configuration

        Returns:
            Dict with success, scraped_file path, pages_scraped, and error (if failed)
        """
        try:
            # Use deepr's scraping infrastructure
            results = scrape_for_company_research(company_url=company_url, company_name=company_name, config=config)

            if not results["success"]:
                return {
                    "success": False,
                    "error": results.get("error", "Scraping failed"),
                }

            # Save scraped content to temporary file for upload
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            temp_file = tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                prefix=f"company_scrape_{company_name.replace(' ', '_')}_{timestamp}_",
                delete=False,
                encoding="utf-8",
            )

            with temp_file:
                # Write scraped content
                temp_file.write(f"# Company Research: {company_name}\n\n")
                temp_file.write(f"**Website**: {company_url}\n")
                temp_file.write(f"**Scraped**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
                temp_file.write(f"**Pages Captured**: {results['pages_scraped']}\n\n")
                temp_file.write("---\n\n")

                # Write synthesis if available
                if results.get("synthesis"):
                    temp_file.write("## Synthesis\n\n")
                    temp_file.write(results["synthesis"])
                    temp_file.write("\n\n---\n\n")

                # Write individual page contents
                temp_file.write("## Scraped Pages\n\n")
                for url, content in results.get("scraped_data", {}).items():
                    temp_file.write(f"### Source: {url}\n\n")
                    temp_file.write(content)
                    temp_file.write("\n\n---\n\n")

            return {
                "success": True,
                "scraped_file": temp_file.name,
                "pages_scraped": results["pages_scraped"],
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _build_research_prompt(self, company_name: str, website: str) -> str:
        """Build the strategic research prompt.

        Args:
            company_name: Company name
            website: Company website

        Returns:
            Strategic research prompt string
        """
        prompt = f"""RESEARCH REQUEST: Strategic Company Overview for Consulting Prep

The goal is to deeply understand {company_name} ({website}) in order to help them. We want to know who they are, what they do, what makes them unique, and what strategic context they operate in. What's happening in their industry? What do their leadership and board care about? What pressures or opportunities shape their next moves? The output should equip us to walk into a discovery conversation with credibility and immediately start identifying where we can add value.

Build this as a consultant-grade overview using the scraped website content provided as primary source, supplemented with publicly available sources (press releases, earnings calls, trusted databases, industry reports). If financials aren't public, use estimates (e.g., "Estimated ~$75M revenue, ZoomInfo") and label them clearly. Don't include inline citations or references.

Use the following section structure and format it cleanly:

## Executive Summary
Brief overview (2-3 paragraphs) capturing the essence of the company, its market position, and strategic context.

## Detailed Products and Services
What they offer, organized by category if diverse. Be specific about offerings, not generic descriptions.

## Unique Selling Proposition
What differentiates them in their industry? Focus on competitive advantages and unique strengths.

## Mission and Vision
Their stated or inferred guiding principles. What they aspire to achieve.

## Company History
Key milestones, founding details, and evolution over time. Include significant pivot points.

## Key Achievements
Growth milestones, awards, innovation, market impact. Quantify where possible.

## Target Audience
Primary customer segments, beneficiaries, stakeholders. Be specific about who they serve.

## Financial Overview
Revenue estimates, funding, financial structure. Label estimates clearly (e.g., "Estimated ~$50M ARR").

## Key Business Drivers and Strategic KPIs
What metrics and factors drive their success? Use industry-appropriate terminology.

## SWOT Analysis
**Strengths**: Internal advantages and capabilities
**Weaknesses**: Internal limitations and challenges
**Opportunities**: External favorable conditions
**Threats**: External risks and competitive pressures

---

FORMATTING INSTRUCTIONS:
- Write in full paragraphs unless bullets help clarity
- Use business consultant tone: analytical, direct, professional
- No inline citations (sources provided separately)
- Use section headers exactly as specified above
- Include specific numbers, names, and examples where available
- Label all estimates clearly
- Keep focus on strategic insights, not surface-level descriptions

The scraped website content is attached as a document. Use it as your primary source for current information about the company, and supplement with web research for industry context, competitive positioning, and strategic analysis."""

        return prompt
