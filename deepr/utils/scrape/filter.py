"""LLM-guided link filtering for intelligent crawling."""

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class LinkFilter:
    """Filters links using LLM to identify relevant pages."""

    def __init__(self, llm_client=None):
        """
        Initialize link filter.

        Args:
            llm_client: Optional LLM client for scoring
        """
        self.llm_client = llm_client

    def filter_links(
        self,
        links: List[Dict[str, str]],
        purpose: str,
        company_name: Optional[str] = None,
        max_links: int = 20,
    ) -> List[Dict[str, str]]:
        """
        Filter links using LLM to identify most relevant.

        Args:
            links: List of link dicts with url, text, context
            purpose: Purpose of scraping (company research, documentation, etc)
            company_name: Optional company name for context
            max_links: Maximum links to return

        Returns:
            Filtered and scored list of links
        """
        if not links:
            return []

        # If few links, return all
        if len(links) <= max_links:
            logger.info(f"Only {len(links)} links, no filtering needed")
            return links

        logger.info(f"Filtering {len(links)} links down to {max_links} using LLM")

        # Create filtering prompt
        prompt = self._create_filter_prompt(links, purpose, company_name)

        try:
            # Get LLM scores
            scores = self._get_llm_scores(prompt)

            # Score and rank links
            scored_links = self._score_links(links, scores)

            # Return top N
            filtered = scored_links[:max_links]
            logger.info(f"Filtered to {len(filtered)} most relevant links")

            return filtered

        except Exception as e:
            # Silently fall back to heuristics if LLM not available
            logger.debug(f"LLM filtering not available, using heuristics: {e}")
            return self._heuristic_filter(links, purpose, max_links)

    def _create_filter_prompt(
        self,
        links: List[Dict[str, str]],
        purpose: str,
        company_name: Optional[str] = None,
    ) -> str:
        """Create prompt for LLM link filtering."""

        # Format links for prompt
        formatted_links = []
        for i, link in enumerate(links, 1):
            text = link.get("text", "")[:100]
            url = link["url"]
            formatted_links.append(f"{i}. {url}\n   Text: {text}")

        links_str = "\n".join(formatted_links)

        # Purpose-specific instructions
        if purpose == "company research":
            focus = """Focus on pages that reveal:
- What the company does (products, services)
- How they position themselves (about, mission, vision)
- Who they serve (customers, case studies)
- Company information (team, investors, news)
- Pricing and business model

Prioritize: About, Products, Solutions, Customers, Pricing, Team, Blog, News
Deprioritize: Support, Help, Contact, Careers, Legal, Terms, Privacy"""

        elif purpose == "documentation":
            focus = """Focus on pages that contain:
- Getting started guides
- API references
- Tutorials and examples
- Concepts and architecture
- Installation and setup
- Feature documentation

Prioritize: Docs, Guide, Tutorial, API, Reference, Examples
Deprioritize: Blog, News, Company, About, Careers"""

        elif purpose == "competitive intel":
            focus = """Focus on pages that reveal:
- Product features and capabilities
- Pricing and packaging
- Customer testimonials
- Recent announcements
- Integrations and partnerships
- Market positioning

Prioritize: Features, Pricing, Customers, News, Partners, Integrations
Deprioritize: Support, Careers, Legal"""

        else:
            focus = "Focus on pages most relevant to the research purpose"

        company_context = f" for {company_name}" if company_name else ""

        prompt = f"""You are analyzing links{company_context} to identify the most relevant pages for {purpose}.

{focus}

Links to evaluate:
{links_str}

For each link, assign a relevance score from 0-10 where:
10 = Critical (must scrape)
7-9 = High relevance (very useful)
4-6 = Medium relevance (moderately useful)
1-3 = Low relevance (marginally useful)
0 = Not relevant (skip)

Return ONLY a JSON array of scores in the same order as the links:
[score1, score2, score3, ...]

Example: [9, 7, 0, 10, 3, 8, 0, 6]

JSON array of scores:"""

        return prompt

    def _get_llm_scores(self, prompt: str) -> List[int]:
        """
        Get scores from LLM.

        Args:
            prompt: Filtering prompt

        Returns:
            List of scores (0-10)
        """
        if not self.llm_client:
            # LLM client not configured - use heuristic fallback silently
            raise AttributeError("No LLM client configured")

        response_text = self.llm_client(prompt)

        # Parse JSON response
        try:
            # Extract JSON array from response
            # Handle cases where LLM adds explanation
            if "[" in response_text:
                json_start = response_text.index("[")
                json_end = response_text.rindex("]") + 1
                json_str = response_text[json_start:json_end]
                scores = json.loads(json_str)
                return scores
            else:
                raise ValueError("No JSON array found in response")

        except Exception as e:
            logger.error(f"Failed to parse LLM scores: {e}")
            logger.error(f"Response was: {response_text}")
            raise

    def _score_links(
        self,
        links: List[Dict[str, str]],
        scores: List[int],
    ) -> List[Dict[str, str]]:
        """
        Apply scores to links and sort by relevance.

        Args:
            links: Original links
            scores: LLM-assigned scores

        Returns:
            Links sorted by score (highest first)
        """
        # Add scores to links
        scored = []
        for link, score in zip(links, scores):
            link_copy = link.copy()
            link_copy["relevance_score"] = score
            scored.append(link_copy)

        # Sort by score (highest first)
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Filter out zero-scored links
        scored = [link for link in scored if link["relevance_score"] > 0]

        return scored

    def _heuristic_filter(
        self,
        links: List[Dict[str, str]],
        purpose: str,
        max_links: int,
    ) -> List[Dict[str, str]]:
        """
        Fallback heuristic filtering when LLM fails.

        Args:
            links: Links to filter
            purpose: Filtering purpose
            max_links: Max links to return

        Returns:
            Filtered links
        """
        logger.info("Using heuristic filtering fallback")

        # Define high-value keywords per purpose
        if purpose == "company research":
            high_value = [
                "about",
                "products",
                "solutions",
                "services",
                "customers",
                "pricing",
                "team",
                "company",
                "mission",
                "vision",
                "news",
            ]
            low_value = [
                "login",
                "signup",
                "support",
                "help",
                "contact",
                "careers",
                "terms",
                "privacy",
                "legal",
                "cookies",
            ]

        elif purpose == "documentation":
            high_value = [
                "docs",
                "documentation",
                "guide",
                "tutorial",
                "api",
                "reference",
                "getting-started",
                "quickstart",
                "examples",
            ]
            low_value = ["blog", "news", "about", "company", "careers", "legal"]

        elif purpose == "competitive intel":
            high_value = [
                "features",
                "pricing",
                "customers",
                "integrations",
                "partners",
                "news",
                "press",
                "case-studies",
            ]
            low_value = ["careers", "legal", "support", "help", "contact"]

        else:
            # Generic filtering
            high_value = ["about", "products", "services", "docs"]
            low_value = ["login", "signup", "legal", "terms", "privacy"]

        # Score links by keywords
        scored = []
        for link in links:
            url_lower = link["url"].lower()
            text_lower = link.get("text", "").lower()

            score = 0

            # Add points for high-value keywords
            for keyword in high_value:
                if keyword in url_lower or keyword in text_lower:
                    score += 2

            # Subtract points for low-value keywords
            for keyword in low_value:
                if keyword in url_lower or keyword in text_lower:
                    score -= 3

            link_copy = link.copy()
            link_copy["relevance_score"] = max(0, score)
            scored.append(link_copy)

        # Sort and filter
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return [link for link in scored if link["relevance_score"] > 0][:max_links]


class SmartCrawler:
    """Intelligent crawler that uses LLM filtering to guide exploration."""

    def __init__(
        self,
        fetcher,
        link_extractor,
        link_filter,
        content_extractor,
        deduplicator,
        config,
    ):
        """
        Initialize smart crawler.

        Args:
            fetcher: ContentFetcher instance
            link_extractor: LinkExtractor instance
            link_filter: LinkFilter instance
            content_extractor: ContentExtractor instance
            deduplicator: PageDeduplicator instance
            config: ScrapeConfig instance
        """
        self.fetcher = fetcher
        self.link_extractor = link_extractor
        self.link_filter = link_filter
        self.content_extractor = content_extractor
        self.deduplicator = deduplicator
        self.config = config

    def crawl(
        self,
        base_url: str,
        purpose: str = "company research",
        company_name: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Crawl a website intelligently.

        Args:
            base_url: Starting URL
            purpose: Crawling purpose
            company_name: Optional company name

        Returns:
            Dict of {url: content}
        """
        logger.info(f"Starting smart crawl of {base_url}")

        results = {}
        queue = [(base_url, 0)]  # (url, depth)
        visited = set()

        while queue and len(results) < self.config.max_pages:
            url, depth = queue.pop(0)

            # Check depth limit
            if depth > self.config.max_depth:
                logger.debug(f"Skipping {url} - depth {depth} exceeds limit")
                continue

            # Check if already visited
            if url in visited or self.deduplicator.is_duplicate(url):
                logger.debug(f"Skipping {url} - already visited")
                continue

            visited.add(url)

            # Fetch page
            logger.info(f"Fetching: {url} (depth {depth})")
            fetch_result = self.fetcher.fetch(url)

            if not fetch_result.success:
                logger.warning(f"Failed to fetch {url}: {fetch_result.error}")
                continue

            # Extract content
            content = self.content_extractor.extract_main_content(fetch_result.html)
            content_hash = self.content_extractor.compute_content_hash(content)

            # Check content deduplication
            if self.deduplicator.is_duplicate(url, content_hash):
                logger.debug(f"Skipping {url} - duplicate content")
                continue

            # Store result
            results[url] = content
            self.deduplicator.mark_seen(url, content_hash)
            logger.info(f"Scraped {url}: {len(content)} chars")

            # Extract links for next level
            if depth < self.config.max_depth:
                links = self.link_extractor.extract_links(fetch_result.html, internal_only=True)

                if links:
                    # Filter with exclusions
                    links = self.link_extractor.filter_excluded(links)

                    # LLM-guided filtering
                    if links:
                        filtered = self.link_filter.filter_links(
                            links,
                            purpose=purpose,
                            company_name=company_name,
                            max_links=10,
                        )

                        # Add to queue
                        for link in filtered:
                            queue.append((link["url"], depth + 1))

                        logger.info(f"Added {len(filtered)} links to queue from {url}")

        logger.info(f"Crawl complete: {len(results)} pages scraped")
        return results
