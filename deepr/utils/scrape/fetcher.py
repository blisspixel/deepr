"""Adaptive content fetcher - tries multiple strategies until content is retrieved."""

import asyncio
import json
import logging
import random
import time
from typing import Optional
from urllib.parse import urlparse

import requests

from deepr.utils.security import SSRFError, validate_url

from .config import USER_AGENTS, ScrapeConfig

logger = logging.getLogger(__name__)

# Check if Playwright is available
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


class FetchResult:
    """Result of a fetch operation."""

    def __init__(
        self,
        url: str,
        content: Optional[str] = None,
        html: Optional[str] = None,
        strategy: Optional[str] = None,
        success: bool = False,
        error: Optional[str] = None,
    ):
        self.url = url
        self.content = content  # Clean text content
        self.html = html  # Raw HTML
        self.strategy = strategy  # Which strategy worked
        self.success = success
        self.error = error


class ContentFetcher:
    """Adaptive content fetcher with multiple fallback strategies."""

    def __init__(self, config: Optional[ScrapeConfig] = None):
        """
        Initialize content fetcher.

        Args:
            config: Scraping configuration (uses defaults if None)
        """
        self.config = config or ScrapeConfig.from_env()
        self.last_request_time = {}

    def fetch(self, url: str) -> FetchResult:
        """
        Fetch content from URL using adaptive strategy chain.

        Tries strategies in order until content is retrieved:
        1. Playwright (handles JS, modern sites - preferred)
        2. HTTP (fast fallback for simple sites)
        3. Selenium headless (legacy fallback)
        4. Archive.org (historical fallback)

        Args:
            url: URL to fetch

        Returns:
            FetchResult with content and metadata
        """
        logger.info(f"Fetching: {url}")

        # Security: Validate URL to prevent SSRF attacks
        try:
            validate_url(url, allow_private=False)
        except SSRFError as e:
            logger.warning(f"SSRF protection blocked URL: {url} - {e}")
            return FetchResult(
                url=url,
                success=False,
                error=f"URL blocked for security reasons: {e}",
            )

        # Rate limiting
        self._rate_limit(url)

        # Check robots.txt if configured
        if self.config.respect_robots and not self._check_robots(url):
            return FetchResult(
                url=url,
                success=False,
                error="Blocked by robots.txt",
            )

        # Try strategies in order - Playwright first for modern JS sites
        strategies = []

        # Playwright is preferred for JS-heavy sites (most modern sites)
        if PLAYWRIGHT_AVAILABLE:
            strategies.append(("Playwright", self._fetch_playwright))

        # HTTP as fast fallback for simple sites
        if self.config.try_http:
            strategies.append(("HTTP", self._fetch_http))

        # Selenium as legacy fallback
        if self.config.try_selenium:
            strategies.append(("Selenium Headless", self._fetch_selenium_headless))

        # Archive.org as last resort
        if self.config.try_archive:
            strategies.append(("Archive.org", self._fetch_archive))

        for strategy_name, strategy_func in strategies:
            logger.info(f"Trying strategy: {strategy_name}")
            result = strategy_func(url)
            if result.success:
                logger.info(f"Success with {strategy_name}")
                return result
            logger.warning(f"{strategy_name} failed: {result.error}")

        # All strategies failed
        return FetchResult(
            url=url,
            success=False,
            error="All fetch strategies failed",
        )

    def _rate_limit(self, url: str):
        """Apply rate limiting per host."""
        host = urlparse(url).netloc
        last_time = self.last_request_time.get(host, 0)
        elapsed = time.time() - last_time

        if elapsed < self.config.rate_limit:
            sleep_time = self.config.rate_limit - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s for {host}")
            time.sleep(sleep_time)

        self.last_request_time[host] = time.time()

    def _check_robots(self, url: str) -> bool:
        """
        Check robots.txt for permission.

        Args:
            url: URL to check

        Returns:
            True if allowed (or can't determine), False if disallowed
        """
        # TODO: Implement robots.txt checking
        # For now, log warning only
        if not self.config.respect_robots:
            logger.debug(f"robots.txt check disabled for {url}")
            return True

        logger.warning(f"robots.txt checking not implemented yet for {url}")
        logger.warning("Proceeding anyway - set respect_robots=True to enforce")
        return True

    def _fetch_http(self, url: str) -> FetchResult:
        """
        Fetch using simple HTTP request.

        Args:
            url: URL to fetch

        Returns:
            FetchResult
        """
        headers = {
            "User-Agent": self.config.user_agent or random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        for attempt in range(self.config.max_retries):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=self.config.timeout,
                    allow_redirects=True,
                )
                response.raise_for_status()

                # SSRF: validate final URL after redirects
                final_url = response.url
                if final_url != url:
                    try:
                        validate_url(final_url, allow_private=False)
                    except SSRFError:
                        logger.warning("SSRF protection blocked redirect target: %s", final_url)
                        return FetchResult(
                            url=url,
                            success=False,
                            error=f"Redirect target blocked for security reasons: {final_url}",
                        )

                return FetchResult(
                    url=url,
                    html=response.text,
                    content=response.text,  # Will be cleaned by extractor
                    strategy="HTTP",
                    success=True,
                )

            except requests.exceptions.RequestException as e:
                logger.debug(f"HTTP attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff

        return FetchResult(
            url=url,
            success=False,
            error="HTTP request failed after retries",
        )

    def _fetch_playwright(self, url: str) -> FetchResult:
        """
        Fetch using Playwright (handles JS-heavy modern sites).

        Args:
            url: URL to fetch

        Returns:
            FetchResult
        """
        if not PLAYWRIGHT_AVAILABLE:
            return FetchResult(
                url=url,
                success=False,
                error="Playwright not installed (pip install playwright && playwright install chromium)",
            )

        # Check if we're already in an async context
        try:
            asyncio.get_running_loop()
            # We're in an async context - use nest_asyncio or thread pool
            # Thread pool is safer and doesn't require extra dependencies
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(self._fetch_playwright_sync_wrapper, url)
                return future.result(timeout=self.config.timeout + 30)
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(self._fetch_playwright_async(url))

    def _fetch_playwright_sync_wrapper(self, url: str) -> FetchResult:
        """Wrapper to run async playwright in a new event loop (for thread pool)."""
        return asyncio.run(self._fetch_playwright_async(url))

    async def _fetch_playwright_async(self, url: str) -> FetchResult:
        """Async Playwright fetch implementation."""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.config.user_agent or random.choice(USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()

                try:
                    # Navigate - use domcontentloaded instead of networkidle
                    # (networkidle can timeout on sites with continuous activity)
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout * 1000)

                    # Wait for body to be present
                    await page.wait_for_selector("body", timeout=5000)

                    # Small delay for JS to render
                    await page.wait_for_timeout(2000)

                    # Get the rendered HTML
                    html = await page.content()

                    return FetchResult(
                        url=url,
                        html=html,
                        content=html,
                        strategy="Playwright",
                        success=True,
                    )
                finally:
                    await browser.close()

        except Exception as e:
            return FetchResult(
                url=url,
                success=False,
                error=f"Playwright failed: {e}",
            )

    def _fetch_selenium_headless(self, url: str) -> FetchResult:
        """
        Fetch using Selenium in headless mode.

        Args:
            url: URL to fetch

        Returns:
            FetchResult
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            return FetchResult(
                url=url,
                success=False,
                error="Selenium not installed (pip install selenium webdriver-manager)",
            )

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"user-agent={self.config.user_agent}")

        driver = None
        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.set_page_load_timeout(self.config.timeout)
            driver.get(url)

            # Wait for content to load
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            html = driver.page_source

            return FetchResult(
                url=url,
                html=html,
                content=html,
                strategy="Selenium Headless",
                success=True,
            )

        except Exception as e:
            return FetchResult(
                url=url,
                success=False,
                error=f"Selenium headless failed: {e}",
            )
        finally:
            if driver:
                driver.quit()

    def _fetch_selenium_visible(self, url: str) -> FetchResult:
        """
        Fetch using Selenium with visible browser (for detection bypass).

        Args:
            url: URL to fetch

        Returns:
            FetchResult
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            return FetchResult(
                url=url,
                success=False,
                error="Selenium not installed",
            )

        options = Options()
        options.add_argument(f"user-agent={self.config.user_agent}")
        # Not headless - visible browser

        driver = None
        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.set_page_load_timeout(self.config.timeout)
            driver.get(url)

            # Wait for content
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            # Small delay to appear more human-like
            time.sleep(random.uniform(1.0, 2.0))

            html = driver.page_source

            return FetchResult(
                url=url,
                html=html,
                content=html,
                strategy="Selenium Visible",
                success=True,
            )

        except Exception as e:
            return FetchResult(
                url=url,
                success=False,
                error=f"Selenium visible failed: {e}",
            )
        finally:
            if driver:
                driver.quit()

    def _fetch_pdf_render(self, url: str) -> FetchResult:
        """
        Fetch by rendering page to PDF and extracting text (nuclear option).

        Args:
            url: URL to fetch

        Returns:
            FetchResult
        """
        # TODO: Implement PDF rendering
        # Would use Chrome's print-to-PDF capability
        return FetchResult(
            url=url,
            success=False,
            error="PDF render not implemented yet",
        )

    def _fetch_archive(self, url: str) -> FetchResult:
        """
        Fetch from archive.org Wayback Machine.

        Args:
            url: URL to fetch

        Returns:
            FetchResult
        """
        try:
            # Try to get latest snapshot
            archive_url = f"https://archive.org/wayback/available?url={url}"
            response = requests.get(archive_url, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data.get("archived_snapshots", {}).get("closest"):
                snapshot_url = data["archived_snapshots"]["closest"]["url"]

                # Fetch the archived page
                snapshot_response = requests.get(snapshot_url, timeout=self.config.timeout)
                snapshot_response.raise_for_status()

                return FetchResult(
                    url=url,
                    html=snapshot_response.text,
                    content=snapshot_response.text,
                    strategy="Archive.org",
                    success=True,
                )

            return FetchResult(
                url=url,
                success=False,
                error="No archive.org snapshot available",
            )

        except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
            return FetchResult(
                url=url,
                success=False,
                error=f"Archive.org fetch failed: {e}",
            )
