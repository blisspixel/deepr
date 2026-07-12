"""Configuration for web scraping."""

import os

from deepr import __version__

DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ScrapeConfig:
    """Configuration for web scraping behavior."""

    def __init__(
        self,
        respect_robots: bool = False,
        rate_limit: float = 1.0,
        max_depth: int = 2,
        max_pages: int = 20,
        timeout: int = 30,
        max_retries: int = 3,
        try_http: bool = True,
        try_selenium: bool = True,
        try_pdf: bool = False,
        try_archive: bool = True,
        log_strategy_failures: bool = True,
        user_agent: str | None = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ):
        """
        Initialize scraping configuration.

        Args:
            respect_robots: Enforce robots.txt rules (default: False for research)
            rate_limit: Seconds between requests (default: 1.0)
            max_depth: Maximum crawl depth (default: 2)
            max_pages: Maximum pages to scrape (default: 20)
            timeout: Request timeout in seconds (default: 30)
            max_retries: Retry attempts per strategy (default: 3)
            try_http: Attempt HTTP fetching (default: True)
            try_selenium: Attempt Selenium rendering (default: True)
            try_pdf: Attempt PDF rendering (expensive, default: False)
            try_archive: Attempt archive.org fallback (default: True)
            log_strategy_failures: Log generic per-strategy failures. Disable
                when a caller renders richer structured source diagnostics.
            user_agent: Custom user agent string
            max_response_bytes: Maximum decompressed response body size in bytes
        """
        self.respect_robots = respect_robots
        self.rate_limit = rate_limit
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.timeout = timeout
        self.max_retries = max_retries
        self.try_http = try_http
        self.try_selenium = try_selenium
        self.try_pdf = try_pdf
        self.try_archive = try_archive
        self.log_strategy_failures = log_strategy_failures
        self.user_agent = user_agent or self._default_user_agent()
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        self.max_response_bytes = max_response_bytes

    @staticmethod
    def _default_user_agent() -> str:
        """Get default user agent string."""
        return f"deepr/{__version__} (Research; +https://github.com/blisspixel/deepr)"

    @classmethod
    def from_env(cls) -> "ScrapeConfig":
        """Load configuration from environment variables."""
        return cls(
            respect_robots=os.getenv("SCRAPE_RESPECT_ROBOTS", "false").lower() == "true",
            rate_limit=float(os.getenv("SCRAPE_RATE_LIMIT", "1.0") or "1.0"),
            max_depth=int(os.getenv("SCRAPE_MAX_DEPTH", "2") or "2"),
            max_pages=int(os.getenv("SCRAPE_MAX_PAGES", "20") or "20"),
            timeout=int(os.getenv("SCRAPE_TIMEOUT", "30") or "30"),
            max_retries=int(os.getenv("SCRAPE_MAX_RETRIES", "3") or "3"),
            try_http=os.getenv("SCRAPE_TRY_HTTP", "true").lower() == "true",
            try_selenium=os.getenv("SCRAPE_TRY_SELENIUM", "true").lower() == "true",
            try_pdf=os.getenv("SCRAPE_TRY_PDF", "false").lower() == "true",
            try_archive=os.getenv("SCRAPE_TRY_ARCHIVE", "true").lower() == "true",
            user_agent=os.getenv("SCRAPE_USER_AGENT"),
            max_response_bytes=int(
                os.getenv("SCRAPE_MAX_RESPONSE_BYTES", str(DEFAULT_MAX_RESPONSE_BYTES))
                or str(DEFAULT_MAX_RESPONSE_BYTES)
            ),
        )

    def as_respectful(self) -> "ScrapeConfig":
        """Return a copy with respectful settings."""
        return ScrapeConfig(
            respect_robots=True,
            rate_limit=2.0,  # Slower
            max_depth=self.max_depth,
            max_pages=self.max_pages,
            timeout=self.timeout,
            max_retries=1,  # Fewer retries
            try_http=True,
            try_selenium=False,  # No aggressive tactics
            try_pdf=False,
            try_archive=False,
            log_strategy_failures=self.log_strategy_failures,
            user_agent=self.user_agent,
            max_response_bytes=self.max_response_bytes,
        )

    def as_force(self) -> "ScrapeConfig":
        """Return a copy with maximum aggression."""
        return ScrapeConfig(
            respect_robots=False,
            rate_limit=0.5,  # Faster
            max_depth=self.max_depth + 1,
            max_pages=self.max_pages * 2,
            timeout=self.timeout,
            max_retries=5,  # More retries
            try_http=True,
            try_selenium=True,
            try_pdf=True,  # Try everything
            try_archive=True,
            log_strategy_failures=self.log_strategy_failures,
            user_agent=self.user_agent,
            max_response_bytes=self.max_response_bytes,
        )


# User agent rotation for variety
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]
