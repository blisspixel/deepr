"""High-level scraping API for easy use."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .config import ScrapeConfig
from .extractor import ContentExtractor, LinkExtractor, PageDeduplicator
from .fetcher import ContentFetcher
from .filter import LinkFilter, SmartCrawler
from .synthesizer import ContentSynthesizer

logger = logging.getLogger(__name__)


def scrape_website(
    url: str,
    purpose: str = "company research",
    company_name: Optional[str] = None,
    config: Optional[ScrapeConfig] = None,
    synthesize: bool = True,
    save_to: Optional[str] = None,
) -> Dict[str, any]:
    """
    Scrape a website with intelligent filtering and synthesis.

    This is the main entry point for web scraping. It handles the complete workflow:
    1. Crawl website with LLM-guided link filtering
    2. Extract and clean content
    3. Synthesize insights (optional)
    4. Save results (optional)

    Args:
        url: Base URL to scrape
        purpose: Purpose of scraping (company research, documentation, competitive intel)
        company_name: Optional company name for context
        config: Optional scraping configuration (uses defaults if None)
        synthesize: Whether to synthesize scraped content into insights
        save_to: Optional path to save results

    Returns:
        Dict with scraped content and synthesis results

    Example:
        >>> from deepr.utils.scrape import scrape_website
        >>>
        >>> # Scrape company website
        >>> results = scrape_website(
        ...     "https://example.com",
        ...     purpose="company research",
        ...     company_name="Example Corp",
        ... )
        >>>
        >>> print(f"Scraped {results['pages_scraped']} pages")
        >>> print(results['insights'])
    """
    logger.info(f"Scraping {url} for {purpose}")

    # Use default config if not provided
    if config is None:
        config = ScrapeConfig.from_env()

    # Initialize components
    fetcher = ContentFetcher(config)
    link_extractor = LinkExtractor(url)
    content_extractor = ContentExtractor()
    deduplicator = PageDeduplicator()
    link_filter = LinkFilter()

    # Create smart crawler
    crawler = SmartCrawler(
        fetcher=fetcher,
        link_extractor=link_extractor,
        link_filter=link_filter,
        content_extractor=content_extractor,
        deduplicator=deduplicator,
        config=config,
    )

    # Crawl website
    scraped_data = crawler.crawl(
        base_url=url,
        purpose=purpose,
        company_name=company_name,
    )

    if not scraped_data:
        logger.error("No content was scraped")
        return {
            "success": False,
            "error": "No content retrieved",
            "url": url,
        }

    logger.info(f"Successfully scraped {len(scraped_data)} pages")

    # Build results
    results = {
        "success": True,
        "url": url,
        "purpose": purpose,
        "company_name": company_name,
        "pages_scraped": len(scraped_data),
        "scraped_urls": list(scraped_data.keys()),
        "scraped_data": scraped_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Synthesize if requested
    if synthesize:
        logger.info("Synthesizing scraped content...")
        synthesizer = ContentSynthesizer()

        synthesis_result = synthesizer.synthesize(
            company_name=company_name or "Unknown",
            base_url=url,
            scraped_data=scraped_data,
            purpose=purpose,
        )

        if synthesis_result["success"]:
            results["insights"] = synthesis_result["insights"]
            logger.info("Synthesis complete")
        else:
            logger.warning(f"Synthesis failed: {synthesis_result.get('error')}")
            results["synthesis_error"] = synthesis_result.get("error")

    # Save if requested
    if save_to:
        save_path = Path(save_to)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w", encoding="utf-8") as f:
            # Don't save full HTML, just insights and metadata
            save_data = {
                "url": results["url"],
                "purpose": results["purpose"],
                "company_name": results["company_name"],
                "pages_scraped": results["pages_scraped"],
                "scraped_urls": results["scraped_urls"],
                "timestamp": results["timestamp"],
            }

            if "insights" in results:
                save_data["insights"] = results["insights"]

            json.dump(save_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to {save_path}")
        results["saved_to"] = str(save_path)

    return results


def scrape_for_company_research(
    company_url: str,
    company_name: str,
    save_dir: Optional[str] = None,
) -> Dict[str, any]:
    """
    Scrape a company website for research purposes.

    Convenience function optimized for company research.

    Args:
        company_url: Company website URL
        company_name: Company name
        save_dir: Optional directory to save results

    Returns:
        Scraping and synthesis results

    Example:
        >>> results = scrape_for_company_research(
        ...     "https://acmecorp.com",
        ...     "Acme Corp",
        ... )
        >>> print(results['insights'])
    """
    config = ScrapeConfig(
        max_pages=25,
        max_depth=2,
    )

    save_to = None
    if save_dir:
        safe_name = company_name.replace(" ", "_").lower()
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        save_to = f"{save_dir}/{safe_name}_{timestamp}.json"

    return scrape_website(
        url=company_url,
        purpose="company research",
        company_name=company_name,
        config=config,
        synthesize=True,
        save_to=save_to,
    )


def scrape_for_documentation(
    docs_url: str,
    project_name: str,
    save_dir: Optional[str] = None,
) -> Dict[str, any]:
    """
    Scrape a documentation site.

    Convenience function optimized for documentation harvesting.

    Args:
        docs_url: Documentation site URL
        project_name: Project/product name
        save_dir: Optional directory to save results

    Returns:
        Scraping and synthesis results

    Example:
        >>> results = scrape_for_documentation(
        ...     "https://docs.project.com",
        ...     "ProjectX",
        ... )
        >>> # Use results to populate expert knowledge base
    """
    config = ScrapeConfig(
        max_pages=50,  # Docs sites often have many pages
        max_depth=3,  # Deeper for nested docs
    )

    save_to = None
    if save_dir:
        safe_name = project_name.replace(" ", "_").lower()
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        save_to = f"{save_dir}/{safe_name}_docs_{timestamp}.json"

    return scrape_website(
        url=docs_url,
        purpose="documentation",
        company_name=project_name,
        config=config,
        synthesize=True,
        save_to=save_to,
    )
