"""Web scraping utilities for primary source research.

Intelligent, adaptive scraping for company research, documentation harvesting,
and competitive intelligence.
"""

from .config import ScrapeConfig
from .fetcher import ContentFetcher, FetchResult
from .extractor import ContentExtractor, LinkExtractor, PageDeduplicator
from .synthesizer import ContentSynthesizer, ProvenanceTracker
from .filter import LinkFilter, SmartCrawler
from .scraper import scrape_website, scrape_for_company_research, scrape_for_documentation

__all__ = [
    'ScrapeConfig',
    'ContentFetcher',
    'FetchResult',
    'ContentExtractor',
    'LinkExtractor',
    'PageDeduplicator',
    'ContentSynthesizer',
    'ProvenanceTracker',
    'LinkFilter',
    'SmartCrawler',
    'scrape_website',
    'scrape_for_company_research',
    'scrape_for_documentation',
]
