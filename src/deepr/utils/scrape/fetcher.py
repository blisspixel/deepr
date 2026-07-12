"""Adaptive content fetcher - tries multiple strategies until content is retrieved."""

import asyncio
import json
import logging
import random
import time
from collections.abc import Callable
from enum import Enum
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import requests

from deepr.utils.security import SSRFError, is_safe_url, validate_url

from .config import USER_AGENTS, ScrapeConfig

logger = logging.getLogger(__name__)
MAX_SAFE_REDIRECTS = 5
RESPONSE_CHUNK_BYTES = 64 * 1024
MAX_ARCHIVE_METADATA_BYTES = 256 * 1024
ARCHIVE_SNAPSHOT_HOST = "web.archive.org"

# Check if Playwright is available
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


class FetchFailureCode(str, Enum):
    """Stable machine-readable fetch failure codes."""

    RESPONSE_TOO_LARGE = "response_too_large"


class _ResponseBodyTooLargeError(ValueError):
    """Raised after a response crosses its configured decoded-byte ceiling."""


class FetchResult:
    """Result of a fetch operation."""

    def __init__(
        self,
        url: str,
        content: str | None = None,
        html: str | None = None,
        strategy: str | None = None,
        success: bool = False,
        error: str | None = None,
        security_blocked: bool = False,
        status_code: int = 0,
        response_headers: dict[str, str] | None = None,
        error_code: FetchFailureCode | None = None,
    ):
        self.url = url
        self.content = content  # Clean text content
        self.html = html  # Raw HTML
        self.strategy = strategy  # Which strategy worked
        self.success = success
        self.error = error
        self.security_blocked = security_blocked
        self.status_code = status_code
        self.response_headers = response_headers or {}
        self.error_code = error_code


class ContentFetcher:
    """Adaptive content fetcher with multiple fallback strategies."""

    def __init__(self, config: ScrapeConfig | None = None):
        """
        Initialize content fetcher.

        Args:
            config: Scraping configuration (uses defaults if None)
        """
        self.config = config or ScrapeConfig.from_env()
        self.last_request_time: dict[str, float] = {}

    def _strategy_chain(
        self,
        headers: dict[str, str] | None,
    ) -> list[tuple[str, Callable[[str], FetchResult]]]:
        strategies: list[tuple[str, Callable[[str], FetchResult]]] = []
        if self.config.try_http:
            strategies.append(("HTTP", lambda target: self._fetch_http(target, headers=headers)))
        if PLAYWRIGHT_AVAILABLE and self.config.try_selenium:
            strategies.append(("Playwright", self._fetch_playwright))
        if self.config.try_selenium:
            strategies.append(("Selenium Headless", self._fetch_selenium_headless))
        if self.config.try_archive:
            strategies.append(("Archive.org", self._fetch_archive))
        return strategies

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        """
        Fetch content from URL using adaptive strategy chain.

        Tries strategies in order until content is retrieved:
        1. HTTP (fast default for simple/static sites)
        2. Playwright (handles JS-heavy modern sites)
        3. Selenium headless (legacy fallback)
        4. Archive.org (historical fallback)

        Args:
            url: URL to fetch
            headers: Optional HTTP headers for the first HTTP fetch strategy.

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
                security_blocked=True,
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

        # Try strategies in order - HTTP first for speed and deterministic behavior.
        strategies = self._strategy_chain(headers)

        for strategy_name, strategy_func in strategies:
            logger.info(f"Trying strategy: {strategy_name}")
            result = strategy_func(url)
            if result.success:
                logger.info(f"Success with {strategy_name}")
                return result
            if result.security_blocked:
                return result
            if result.error_code is FetchFailureCode.RESPONSE_TOO_LARGE:
                return result
            if getattr(self.config, "log_strategy_failures", True):
                logger.warning(f"{strategy_name} failed: {result.error}")

        # All strategies failed
        return FetchResult(
            url=url,
            success=False,
            error="All fetch strategies failed",
        )

    def _rate_limit(self, url: str) -> None:
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
        # Robots.txt enforcement is not implemented in this fetcher yet; callers
        # that need strict crawl compliance should disable fetching upstream.
        if not self.config.respect_robots:
            logger.debug(f"robots.txt check disabled for {url}")
            return True

        logger.warning(f"robots.txt checking not implemented yet for {url}")
        logger.warning("Proceeding anyway - set respect_robots=True to enforce")
        return True

    def _fetch_http(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        """
        Fetch using simple HTTP request.

        Args:
            url: URL to fetch

        Returns:
            FetchResult
        """
        request_headers = {
            "User-Agent": self.config.user_agent or random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        request_headers.update(headers or {})

        for attempt in range(self.config.max_retries):
            try:
                current_url = url
                for redirect_count in range(MAX_SAFE_REDIRECTS + 1):
                    response = requests.get(
                        current_url,
                        headers=request_headers,
                        timeout=self.config.timeout,
                        allow_redirects=False,
                        stream=True,
                    )
                    if not response.is_redirect:
                        break
                    try:
                        redirect_target = self._redirect_target(response, current_url, url, redirect_count)
                    finally:
                        response.close()
                    if isinstance(redirect_target, FetchResult):
                        return redirect_target
                    current_url = redirect_target
                else:
                    return FetchResult(url=url, success=False, error="Too many redirects")

                try:
                    if response.status_code == 304:
                        return FetchResult(
                            url=current_url,
                            strategy="HTTP",
                            success=True,
                            status_code=response.status_code,
                            response_headers=dict(response.headers),
                        )

                    response.raise_for_status()
                    text = self._read_response_text(response, self.config.max_response_bytes)
                    return FetchResult(
                        url=current_url,
                        html=text,
                        content=text,  # Will be cleaned by extractor
                        strategy="HTTP",
                        success=True,
                        status_code=response.status_code,
                        response_headers=dict(response.headers),
                    )
                except _ResponseBodyTooLargeError:
                    return self._response_too_large_result(current_url, response, "HTTP")
                finally:
                    response.close()

            except requests.exceptions.RequestException as e:
                logger.debug(f"HTTP attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff

        return FetchResult(
            url=url,
            success=False,
            error="HTTP request failed after retries",
        )

    @staticmethod
    def _redirect_target(
        response: requests.Response,
        current_url: str,
        original_url: str,
        redirect_count: int,
    ) -> str | FetchResult:
        """Validate and return the next redirect target or a terminal failure."""
        location = response.headers.get("Location", "")
        if not location:
            return FetchResult(url=original_url, success=False, error="Redirect missing Location header")
        try:
            next_url = urljoin(current_url, location)
        except ValueError as redirect_error:
            return FetchResult(
                url=original_url,
                success=False,
                error=f"Redirect target blocked for security reasons: {redirect_error}",
                security_blocked=True,
            )
        try:
            validate_url(next_url, allow_private=False)
        except SSRFError as redirect_error:
            logger.warning("SSRF protection blocked redirect target: %s", next_url)
            return FetchResult(
                url=original_url,
                success=False,
                error=f"Redirect target blocked for security reasons: {redirect_error}",
                security_blocked=True,
            )
        if redirect_count >= MAX_SAFE_REDIRECTS:
            return FetchResult(url=original_url, success=False, error="Too many redirects")
        return next_url

    @staticmethod
    def _declared_body_length(response: requests.Response) -> int | None:
        """Return Content-Length only when it describes decoded body bytes."""
        if response.headers.get("Transfer-Encoding"):
            return None
        content_encoding = response.headers.get("Content-Encoding", "").strip().lower()
        if content_encoding and content_encoding != "identity":
            return None
        raw_length = response.headers.get("Content-Length")
        if raw_length is None:
            return None
        try:
            declared_length = int(raw_length)
        except ValueError:
            return None
        return declared_length if declared_length >= 0 else None

    @classmethod
    def _read_response_body(cls, response: requests.Response, limit: int) -> bytearray:
        """Read at most limit plus one decoded bytes from a streamed response."""
        declared_length = cls._declared_body_length(response)
        if declared_length is not None and declared_length > limit:
            raise _ResponseBodyTooLargeError

        body = bytearray()
        chunk_size = min(RESPONSE_CHUNK_BYTES, limit + 1)
        for chunk in response.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue
            remaining = limit + 1 - len(body)
            body.extend(chunk[:remaining])
            if len(body) > limit:
                raise _ResponseBodyTooLargeError
        return body

    @classmethod
    def _read_response_text(cls, response: requests.Response, limit: int) -> str:
        """Read a bounded response and decode it only after the byte check."""
        body = cls._read_response_body(response, limit)
        encoding = response.encoding or "utf-8"
        try:
            return body.decode(encoding, errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")

    def _response_too_large_result(
        self,
        url: str,
        response: requests.Response,
        strategy: str,
        limit: int | None = None,
    ) -> FetchResult:
        response_limit = self.config.max_response_bytes if limit is None else limit
        return FetchResult(
            url=url,
            strategy=strategy,
            success=False,
            error=f"Response body exceeds configured maximum of {response_limit} bytes",
            error_code=FetchFailureCode.RESPONSE_TOO_LARGE,
            status_code=response.status_code,
            response_headers=dict(response.headers),
        )

    @staticmethod
    def _validate_archive_snapshot_start(original_url: str, snapshot_url: object) -> str | FetchResult:
        """Validate an untrusted Wayback snapshot URL before dispatch."""
        if not isinstance(snapshot_url, str):
            return FetchResult(
                url=original_url,
                strategy="Archive.org",
                success=False,
                error="Archive.org snapshot URL is invalid",
                security_blocked=True,
            )
        try:
            snapshot_host = urlparse(snapshot_url).hostname
        except ValueError:
            snapshot_host = None
        if snapshot_host != ARCHIVE_SNAPSHOT_HOST:
            return FetchResult(
                url=original_url,
                strategy="Archive.org",
                success=False,
                error="Archive.org snapshot URL has an unexpected host",
                security_blocked=True,
            )
        try:
            validate_url(snapshot_url, allow_private=False)
        except SSRFError as snapshot_error:
            return FetchResult(
                url=original_url,
                strategy="Archive.org",
                success=False,
                error=f"Archive.org snapshot URL blocked for security reasons: {snapshot_error}",
                security_blocked=True,
            )
        return snapshot_url

    def _fetch_archive_snapshot(self, original_url: str, snapshot_url: object) -> FetchResult:
        """Fetch a Wayback snapshot through bounded, SSRF-checked redirects."""
        validated_start = self._validate_archive_snapshot_start(original_url, snapshot_url)
        if isinstance(validated_start, FetchResult):
            return validated_start

        current_url = validated_start
        for redirect_count in range(MAX_SAFE_REDIRECTS + 1):
            response = requests.get(
                current_url,
                timeout=self.config.timeout,
                allow_redirects=False,
                stream=True,
            )
            if response.is_redirect:
                try:
                    redirect_target = self._redirect_target(response, current_url, original_url, redirect_count)
                finally:
                    response.close()
                if isinstance(redirect_target, FetchResult):
                    redirect_target.strategy = "Archive.org"
                    return redirect_target
                current_url = redirect_target
                continue

            try:
                response.raise_for_status()
                text = self._read_response_text(response, self.config.max_response_bytes)
                return FetchResult(
                    url=original_url,
                    html=text,
                    content=text,
                    strategy="Archive.org",
                    success=True,
                    status_code=response.status_code,
                    response_headers=dict(response.headers),
                )
            except _ResponseBodyTooLargeError:
                return self._response_too_large_result(original_url, response, "Archive.org")
            finally:
                response.close()

        return FetchResult(
            url=original_url,
            strategy="Archive.org",
            success=False,
            error="Too many redirects",
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
        """Async Playwright fetch implementation.

        Blocks SSRF after JavaScript navigation:
        - Per-request routing rejects any request the browser issues to a
          private/loopback/link-local/non-HTTP target, even if it originates
          from JS inside an attacker-controlled public page.
        - After page.goto() completes, page.url is re-validated to catch top-
          level redirects/window.location navigations to internal targets.
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.config.user_agent or random.choice(USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                )

                async def _ssrf_guard(route: Any, request_obj: Any) -> None:
                    """Abort any browser request that targets a private/internal host."""
                    try:
                        target = request_obj.url
                        if not is_safe_url(target, allow_private=False):
                            logger.warning("Playwright SSRF guard blocked %s", target)
                            await route.abort("blockedbyclient")
                            return
                    except Exception as exc:
                        logger.debug("SSRF guard error, aborting request: %s", exc)
                        await route.abort("failed")
                        return
                    await route.continue_()

                await context.route("**/*", _ssrf_guard)
                page = await context.new_page()

                try:
                    # Navigate - use domcontentloaded instead of networkidle
                    # (networkidle can timeout on sites with continuous activity)
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout * 1000)

                    # Re-validate the final URL - JS may have called
                    # window.location = "http://169.254.169.254/..." or a top-
                    # level redirect may have moved us to an internal host.
                    final_url = page.url
                    if final_url and final_url != url:
                        try:
                            validate_url(final_url, allow_private=False)
                        except SSRFError as exc:
                            logger.warning("Playwright final URL blocked: %s (%s)", final_url, exc)
                            return FetchResult(
                                url=url,
                                success=False,
                                error=f"Final URL blocked for security reasons: {final_url}",
                            )

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
            archive_url = f"https://archive.org/wayback/available?{urlencode({'url': url})}"
            response = requests.get(archive_url, timeout=10, stream=True)
            try:
                response.raise_for_status()
                metadata_text = self._read_response_text(response, MAX_ARCHIVE_METADATA_BYTES)
                data = json.loads(metadata_text)
            except _ResponseBodyTooLargeError:
                return self._response_too_large_result(
                    url,
                    response,
                    "Archive.org",
                    limit=MAX_ARCHIVE_METADATA_BYTES,
                )
            finally:
                response.close()
            if data.get("archived_snapshots", {}).get("closest"):
                snapshot_url = data["archived_snapshots"]["closest"]["url"]
                return self._fetch_archive_snapshot(url, snapshot_url)

            return FetchResult(
                url=url,
                success=False,
                error="No archive.org snapshot available",
            )

        except (requests.RequestException, json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError) as e:
            return FetchResult(
                url=url,
                success=False,
                error=f"Archive.org fetch failed: {e}",
            )
