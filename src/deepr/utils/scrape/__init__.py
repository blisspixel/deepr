"""Web scraping utilities for primary source research.

Intelligent, adaptive scraping for company research, documentation harvesting,
and competitive intelligence.
"""

from .config import ScrapeConfig
from .extractor import ContentExtractor, LinkExtractor, PageDeduplicator
from .fetcher import ContentFetcher, FetchResult
from .filter import LinkFilter, SmartCrawler
from .scraper import scrape_for_company_research, scrape_for_documentation, scrape_website
from .synthesizer import ContentSynthesizer, ProvenanceTracker

__all__ = [
    "ContentExtractor",
    "ContentFetcher",
    "ContentSynthesizer",
    "FetchResult",
    "LinkExtractor",
    "LinkFilter",
    "PageDeduplicator",
    "ProvenanceTracker",
    "ScrapeConfig",
    "SmartCrawler",
    "scrape_for_company_research",
    "scrape_for_documentation",
    "scrape_website",
]
