"""Content and link extraction from HTML."""

import hashlib
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class LinkExtractor:
    """Extracts and filters links from HTML."""

    def __init__(self, base_url: str):
        """
        Initialize link extractor.

        Args:
            base_url: Base URL for resolving relative links
        """
        self.base_url = base_url
        self.base_domain = urlparse(base_url).netloc

    def extract_links(self, html: str, internal_only: bool = True) -> list[dict[str, str]]:
        """
        Extract links from HTML.

        Args:
            html: HTML content
            internal_only: Only return links from same domain

        Returns:
            List of dicts with url, text, context
        """
        soup = BeautifulSoup(html, "html.parser")
        links = []
        seen_urls = set()

        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "").strip()
            if not href or href.startswith("#"):
                continue

            # Resolve relative URLs
            full_url = urljoin(self.base_url, href)

            # Filter internal/external
            if internal_only:
                link_domain = urlparse(full_url).netloc
                if link_domain != self.base_domain:
                    continue

            # Deduplicate
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Extract link context
            link_text = tag.get_text(strip=True)
            context = self._get_link_context(tag)

            links.append(
                {
                    "url": full_url,
                    "text": link_text,
                    "context": context,
                }
            )

        logger.info(f"Extracted {len(links)} links from {self.base_url}")
        return links

    def _get_link_context(self, tag) -> str:
        """Get surrounding context for a link."""
        # Try to get parent paragraph or section
        parent = tag.find_parent(["p", "section", "div"])
        if parent:
            return parent.get_text(strip=True)[:200]
        return ""

    def filter_excluded(self, links: list[dict[str, str]]) -> list[dict[str, str]]:
        """
        Filter out commonly irrelevant links.

        Args:
            links: List of link dicts

        Returns:
            Filtered list
        """
        excluded_keywords = [
            "login",
            "signin",
            "signup",
            "register",
            "support",
            "help",
            "contact",
            "terms",
            "privacy",
            "cookies",
            "legal",
            "careers",
            "jobs",
            "apply",
            "cart",
            "checkout",
            "account",
        ]

        filtered = []
        for link in links:
            url_lower = link["url"].lower()
            if not any(keyword in url_lower for keyword in excluded_keywords):
                filtered.append(link)

        logger.info(f"Filtered {len(links)} links to {len(filtered)}")
        return filtered


class ContentExtractor:
    """Extracts clean text content from HTML."""

    def extract_text(self, html: str) -> str:
        """
        Extract clean text content from HTML.

        Args:
            html: Raw HTML

        Returns:
            Clean text content
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Get text
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text

    def extract_main_content(self, html: str) -> str:
        """
        Extract main content using simple heuristics.

        Args:
            html: Raw HTML

        Returns:
            Main content text
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to find main content area
        main_content = None

        # Look for common content containers
        for selector in ["main", "article", '[role="main"]', ".content", "#content"]:
            main_content = soup.select_one(selector)
            if main_content:
                break

        # Fallback to body
        if not main_content:
            main_content = soup.find("body")

        if not main_content:
            return self.extract_text(html)

        # Extract text from main content
        text = main_content.get_text()

        # Clean up
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text

    def extract_metadata(self, html: str) -> dict[str, str]:
        """
        Extract structured metadata from HTML.

        Args:
            html: Raw HTML

        Returns:
            Dict of metadata
        """
        soup = BeautifulSoup(html, "html.parser")
        metadata = {}

        # Title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)

        # Meta description
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag:
            metadata["description"] = desc_tag.get("content", "")

        # Open Graph tags
        og_tags = {
            "og:title": "og_title",
            "og:description": "og_description",
            "og:type": "og_type",
            "og:url": "og_url",
        }
        for og_property, key in og_tags.items():
            tag = soup.find("meta", property=og_property)
            if tag:
                metadata[key] = tag.get("content", "")

        # Author
        author_tag = soup.find("meta", attrs={"name": "author"})
        if author_tag:
            metadata["author"] = author_tag.get("content", "")

        return metadata

    def compute_content_hash(self, content: str) -> str:
        """
        Compute hash of content for deduplication.

        Args:
            content: Text content

        Returns:
            SHA256 hash hex string
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class PageDeduplicator:
    """Deduplicates pages by URL and content hash."""

    def __init__(self):
        self.seen_urls: set[str] = set()
        self.seen_hashes: set[str] = set()

    def is_duplicate(self, url: str, content_hash: Optional[str] = None) -> bool:
        """
        Check if URL or content is duplicate.

        Args:
            url: Page URL
            content_hash: Optional content hash

        Returns:
            True if duplicate
        """
        # Check URL
        normalized_url = self._normalize_url(url)
        if normalized_url in self.seen_urls:
            return True

        # Check content hash if provided
        if content_hash and content_hash in self.seen_hashes:
            return True

        return False

    def mark_seen(self, url: str, content_hash: Optional[str] = None):
        """
        Mark URL and content as seen.

        Args:
            url: Page URL
            content_hash: Optional content hash
        """
        normalized_url = self._normalize_url(url)
        self.seen_urls.add(normalized_url)

        if content_hash:
            self.seen_hashes.add(content_hash)

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for comparison.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL
        """
        # Remove trailing slash
        url = url.rstrip("/")

        # TODO: Remove common tracking parameters / implement parameter filtering

        return url.lower()
