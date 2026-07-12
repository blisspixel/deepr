"""Core tests for scraping utilities.

Tests the fundamental functionality without requiring external dependencies.
"""

import logging
import os
import sys

import pytest
from requests import Response
from requests.exceptions import ChunkedEncodingError

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deepr.utils.scrape import (
    ContentExtractor,
    ContentFetcher,
    FetchFailureCode,
    FetchResult,
    LinkExtractor,
    PageDeduplicator,
    ScrapeConfig,
)
from deepr.utils.scrape.fetcher import MAX_ARCHIVE_METADATA_BYTES
from deepr.utils.security import SSRFError
from tests.unit.scrape_helpers import make_scrape_response


def test_scrape_config():
    """Test configuration creation and modes."""
    print("\n[TEST] ScrapeConfig...")

    # Default config
    config = ScrapeConfig()
    assert config.respect_robots == False, "Default should prioritize content acquisition"
    assert config.rate_limit == 1.0
    assert config.max_depth == 2
    assert config.max_pages == 20
    assert config.max_response_bytes == 8 * 1024 * 1024
    assert FetchFailureCode.RESPONSE_TOO_LARGE == "response_too_large"
    print("  [OK] Default config")

    # Respectful mode
    respectful = config.as_respectful()
    assert respectful.respect_robots == True
    assert respectful.rate_limit == 2.0  # Slower
    assert respectful.try_selenium == False  # No aggressive tactics
    assert respectful.max_response_bytes == config.max_response_bytes
    print("  [OK] Respectful mode")

    # Force mode
    force = config.as_force()
    assert force.respect_robots == False
    assert force.rate_limit == 0.5  # Faster
    assert force.max_retries == 5
    assert force.try_pdf == True
    assert force.max_response_bytes == config.max_response_bytes
    print("  [OK] Force mode")

    print("[PASS] ScrapeConfig\n")


def test_scrape_config_response_ceiling_from_env(monkeypatch):
    monkeypatch.setenv("SCRAPE_MAX_RESPONSE_BYTES", "4096")

    assert ScrapeConfig.from_env().max_response_bytes == 4096
    with pytest.raises(ValueError, match="max_response_bytes must be positive"):
        ScrapeConfig(max_response_bytes=0)


def test_content_extractor():
    """Test content extraction from HTML."""
    print("\n[TEST] ContentExtractor...")

    extractor = ContentExtractor()

    # Test HTML
    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <nav>Navigation</nav>
        <main>
            <h1>Main Content</h1>
            <p>This is the main content of the page.</p>
            <p>It has multiple paragraphs.</p>
        </main>
        <footer>Footer</footer>
        <script>console.log('test');</script>
    </body>
    </html>
    """

    # Extract text
    text = extractor.extract_text(html)
    assert "Main Content" in text
    assert "main content of the page" in text
    assert "Navigation" not in text  # Should be removed
    assert "Footer" not in text  # Should be removed
    assert "console.log" not in text  # Script should be removed
    print("  [OK] Text extraction")

    # Extract main content
    main = extractor.extract_main_content(html)
    assert "Main Content" in main
    assert "main content of the page" in main
    print("  [OK] Main content extraction")

    # Extract metadata
    metadata = extractor.extract_metadata(html)
    assert metadata.get("title") == "Test Page"
    print("  [OK] Metadata extraction")

    # Content hash
    hash1 = extractor.compute_content_hash("test content")
    hash2 = extractor.compute_content_hash("test content")
    hash3 = extractor.compute_content_hash("different content")
    assert hash1 == hash2, "Same content should produce same hash"
    assert hash1 != hash3, "Different content should produce different hash"
    print("  [OK] Content hashing")

    print("[PASS] ContentExtractor\n")


def test_link_extractor():
    """Test link extraction and filtering."""
    print("\n[TEST] LinkExtractor...")

    html = """
    <html>
    <body>
        <a href="/about">About Us</a>
        <a href="/products">Products</a>
        <a href="/login">Login</a>
        <a href="https://external.com">External</a>
        <a href="/terms">Terms</a>
        <a href="#">Hash link</a>
    </body>
    </html>
    """

    extractor = LinkExtractor("https://example.com")

    # Extract internal links
    links = extractor.extract_links(html, internal_only=True)
    assert len(links) > 0
    assert all("example.com" in link["url"] for link in links)
    print(f"  [OK] Extracted {len(links)} internal links")

    # Filter excluded
    filtered = extractor.filter_excluded(links)
    assert not any("login" in link["url"].lower() for link in filtered)
    assert not any("terms" in link["url"].lower() for link in filtered)
    print(f"  [OK] Filtered to {len(filtered)} relevant links")

    print("[PASS] LinkExtractor\n")


def test_page_deduplicator():
    """Test page deduplication."""
    print("\n[TEST] PageDeduplicator...")

    deduper = PageDeduplicator()

    # Check new URL
    assert not deduper.is_duplicate("https://example.com/page1")
    deduper.mark_seen("https://example.com/page1")
    print("  [OK] First URL not duplicate")

    # Check duplicate URL
    assert deduper.is_duplicate("https://example.com/page1")
    print("  [OK] Same URL detected as duplicate")

    # Check with trailing slash normalization
    deduper.mark_seen("https://example.com/page2/")
    assert deduper.is_duplicate("https://example.com/page2")
    print("  [OK] Trailing slash normalization")

    # Check content hash deduplication
    hash1 = "abc123"
    deduper.mark_seen("https://example.com/page3", hash1)
    assert deduper.is_duplicate("https://example.com/different-url", hash1)
    print("  [OK] Content hash deduplication")

    print("[PASS] PageDeduplicator\n")


def test_http_fetcher(monkeypatch):
    """Test HTTP fetching without external network."""
    print("\n[TEST] ContentFetcher fetch...")

    config = ScrapeConfig(
        try_selenium=False,
        try_pdf=False,
        try_archive=False,
        timeout=10,
    )
    fetcher = ContentFetcher(config)
    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", lambda *args, **kwargs: make_scrape_response())

    result = fetcher.fetch("https://example.com")

    assert result.strategy == "HTTP"
    assert result.html is not None
    assert len(result.html) > 100
    print(f"  [OK] Fetch successful via {result.strategy}")
    print(f"  [OK] Got {len(result.html)} chars of HTML")

    print("[PASS] ContentFetcher fetch\n")


@pytest.mark.parametrize(
    ("log_strategy_failures", "warning_expected"),
    [(True, True), (False, False)],
)
def test_strategy_failure_logging_is_caller_controlled(
    monkeypatch,
    caplog,
    log_strategy_failures,
    warning_expected,
):
    config = ScrapeConfig(
        try_selenium=False,
        try_pdf=False,
        try_archive=False,
        rate_limit=0,
        log_strategy_failures=log_strategy_failures,
    )
    fetcher = ContentFetcher(config)
    monkeypatch.setattr("deepr.utils.scrape.fetcher.validate_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        fetcher,
        "_fetch_http",
        lambda _url, headers=None: FetchResult(
            url=_url,
            success=False,
            error="HTTP request failed after retries",
        ),
    )

    with caplog.at_level(logging.WARNING, logger="deepr.utils.scrape.fetcher"):
        result = fetcher.fetch("https://example.com")

    assert result.success is False
    assert ("HTTP failed: HTTP request failed after retries" in caplog.text) is warning_expected


def test_http_fetcher_sends_conditional_headers_and_returns_304(monkeypatch):
    config = ScrapeConfig(
        try_selenium=False,
        try_pdf=False,
        try_archive=False,
        timeout=10,
    )
    fetcher = ContentFetcher(config)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        response = Response()
        response.status_code = 304
        response.url = url
        response._content_consumed = True
        response.headers["ETag"] = '"abc"'
        response.headers["Last-Modified"] = "Wed, 01 Jul 2026 00:00:00 GMT"
        return response

    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", fake_get)

    result = fetcher.fetch(
        "https://example.com",
        headers={
            "If-None-Match": '"abc"',
            "If-Modified-Since": "Wed, 01 Jul 2026 00:00:00 GMT",
        },
    )

    assert result.success is True
    assert result.status_code == 304
    assert result.html is None
    assert calls[0][1]["headers"]["If-None-Match"] == '"abc"'
    assert calls[0][1]["headers"]["If-Modified-Since"] == "Wed, 01 Jul 2026 00:00:00 GMT"
    assert result.response_headers["ETag"] == '"abc"'
    assert calls[0][1]["stream"] is True


class _StreamingResponse(Response):
    """Requests response double that exposes bounded iteration state."""

    def __init__(self, chunks, *, headers=None, status_code=200, encoding="utf-8"):
        super().__init__()
        self.status_code = status_code
        self.headers.update(headers or {})
        self.encoding = encoding
        self.chunks = chunks
        self.yielded_chunks = 0
        self.closed_by_fetcher = False

    def iter_content(self, chunk_size=1, decode_unicode=False):
        del chunk_size, decode_unicode
        for chunk in self.chunks:
            self.yielded_chunks += 1
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        self.closed_by_fetcher = True


def test_http_fetcher_rejects_trustworthy_oversized_content_length(monkeypatch):
    config = ScrapeConfig(
        try_selenium=False,
        try_pdf=False,
        try_archive=False,
        rate_limit=0,
        max_retries=3,
        max_response_bytes=8,
    )
    fetcher = ContentFetcher(config)
    response = _StreamingResponse(
        [AssertionError("body must not be read")],
        headers={"Content-Length": "9"},
    )
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", fake_get)

    result = fetcher.fetch("https://example.com/large")

    assert result.success is False
    assert result.error_code == "response_too_large"
    assert result.error == "Response body exceeds configured maximum of 8 bytes"
    assert result.status_code == 200
    assert response.yielded_chunks == 0
    assert response.closed_by_fetcher is True
    assert len(calls) == 1
    assert calls[0][1]["stream"] is True


@pytest.mark.parametrize(
    "response_headers",
    [
        {"Content-Encoding": "gzip", "Content-Length": "999"},
        {"Transfer-Encoding": "chunked", "Content-Length": "999"},
    ],
)
def test_http_fetcher_stops_encoded_or_chunked_body_after_limit_plus_one(monkeypatch, response_headers):
    config = ScrapeConfig(
        try_selenium=True,
        try_pdf=False,
        try_archive=True,
        rate_limit=0,
        max_response_bytes=8,
    )
    fetcher = ContentFetcher(config)
    response = _StreamingResponse(
        [b"12345678", b"90", AssertionError("stream must stop after limit plus one")],
        headers=response_headers,
    )
    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(
        fetcher,
        "_fetch_selenium_headless",
        lambda _url: (_ for _ in ()).throw(AssertionError("oversized response must stop fallbacks")),
    )
    monkeypatch.setattr(
        fetcher,
        "_fetch_archive",
        lambda _url: (_ for _ in ()).throw(AssertionError("oversized response must stop fallbacks")),
    )

    result = fetcher.fetch("https://example.com/compressed")

    assert result.error_code == "response_too_large"
    assert response.yielded_chunks == 2
    assert response.closed_by_fetcher is True


def test_http_fetcher_retries_stream_read_failures(monkeypatch):
    config = ScrapeConfig(
        try_selenium=False,
        try_pdf=False,
        try_archive=False,
        rate_limit=0,
        max_retries=2,
        max_response_bytes=8,
    )
    fetcher = ContentFetcher(config)
    responses = [
        _StreamingResponse([ChunkedEncodingError("truncated")]),
        _StreamingResponse([b"okay"]),
    ]
    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", lambda *_args, **_kwargs: responses.pop(0))
    monkeypatch.setattr("deepr.utils.scrape.fetcher.time.sleep", lambda _seconds: None)

    result = fetcher.fetch("https://example.com/retry")

    assert result.success is True
    assert result.content == "okay"
    assert responses == []


def test_archive_snapshot_body_uses_response_ceiling(monkeypatch):
    config = ScrapeConfig(
        try_selenium=False,
        try_pdf=False,
        try_archive=True,
        rate_limit=0,
        max_response_bytes=8,
    )
    fetcher = ContentFetcher(config)
    metadata = _StreamingResponse([b'{"archived_snapshots":{"closest":{"url":"https://web.archive.org/page"}}}'])
    snapshot = _StreamingResponse(
        [AssertionError("archive body must not be read")],
        headers={"Content-Length": "9"},
    )
    responses = [metadata, snapshot]
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", fake_get)
    monkeypatch.setattr("deepr.utils.scrape.fetcher.validate_url", lambda target, **_kwargs: target)

    result = fetcher._fetch_archive("https://example.com")

    assert result.error_code == "response_too_large"
    assert result.strategy == "Archive.org"
    assert snapshot.yielded_chunks == 0
    assert metadata.closed_by_fetcher is True
    assert snapshot.closed_by_fetcher is True
    assert all(call[1]["stream"] is True for call in calls)
    assert calls[1][1]["allow_redirects"] is False


def test_archive_metadata_has_independent_small_response_ceiling(monkeypatch):
    config = ScrapeConfig(try_selenium=False, try_pdf=False, try_archive=True, rate_limit=0)
    fetcher = ContentFetcher(config)
    metadata = _StreamingResponse(
        [AssertionError("metadata body must not be read")],
        headers={"Content-Length": str(MAX_ARCHIVE_METADATA_BYTES + 1)},
    )
    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", lambda *_args, **_kwargs: metadata)

    result = fetcher._fetch_archive("https://example.com")

    assert result.error_code == "response_too_large"
    assert result.error == f"Response body exceeds configured maximum of {MAX_ARCHIVE_METADATA_BYTES} bytes"
    assert metadata.yielded_chunks == 0
    assert metadata.closed_by_fetcher is True


def test_archive_rejects_untrusted_snapshot_host_before_dispatch(monkeypatch):
    config = ScrapeConfig(try_selenium=False, try_pdf=False, try_archive=True, rate_limit=0)
    fetcher = ContentFetcher(config)
    metadata = _StreamingResponse([b'{"archived_snapshots":{"closest":{"url":"https://attacker.example/snapshot"}}}'])
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) > 1:
            raise AssertionError("untrusted snapshot host must not be dispatched")
        return metadata

    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", fake_get)

    result = fetcher._fetch_archive("https://example.com")

    assert result.success is False
    assert result.security_blocked is True
    assert result.strategy == "Archive.org"
    assert result.error == "Archive.org snapshot URL has an unexpected host"
    assert len(calls) == 1
    assert metadata.closed_by_fetcher is True


def test_archive_blocks_private_redirect_before_follow(monkeypatch):
    config = ScrapeConfig(try_selenium=False, try_pdf=False, try_archive=True, rate_limit=0)
    fetcher = ContentFetcher(config)
    metadata = _StreamingResponse([b'{"archived_snapshots":{"closest":{"url":"https://web.archive.org/snapshot"}}}'])
    redirect = _StreamingResponse([], status_code=302, headers={"Location": "http://127.0.0.1/admin"})
    responses = [metadata, redirect]
    calls = []
    validated_urls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if not responses:
            raise AssertionError("private redirect target must not be dispatched")
        return responses.pop(0)

    def fake_validate(target, **_kwargs):
        validated_urls.append(target)
        if target.startswith("http://127.0.0.1"):
            raise SSRFError(f"URL is not safe to fetch: {target}")
        return target

    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", fake_get)
    monkeypatch.setattr("deepr.utils.scrape.fetcher.validate_url", fake_validate)

    result = fetcher._fetch_archive("https://example.com")

    assert result.success is False
    assert result.security_blocked is True
    assert result.strategy == "Archive.org"
    assert "Redirect target blocked for security reasons" in (result.error or "")
    assert validated_urls == ["https://web.archive.org/snapshot", "http://127.0.0.1/admin"]
    assert len(calls) == 2
    assert calls[1][1]["allow_redirects"] is False
    assert metadata.closed_by_fetcher is True
    assert redirect.closed_by_fetcher is True


def test_http_fetcher_blocks_private_redirect_before_follow(monkeypatch):
    """Redirect targets are validated before the second request is made."""
    config = ScrapeConfig(
        try_selenium=True,
        try_pdf=False,
        try_archive=True,
        timeout=10,
    )
    fetcher = ContentFetcher(config)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) > 1:
            raise AssertionError("private redirect target must not be requested")
        response = Response()
        response.status_code = 302
        response.url = url
        response._content_consumed = True
        response.headers["Location"] = "http://127.0.0.1/admin"
        return response

    monkeypatch.setattr("deepr.utils.scrape.fetcher.requests.get", fake_get)
    monkeypatch.setattr(
        fetcher,
        "_fetch_selenium_headless",
        lambda _url: (_ for _ in ()).throw(AssertionError("security block must stop Selenium fallback")),
    )
    monkeypatch.setattr(
        fetcher,
        "_fetch_archive",
        lambda _url: (_ for _ in ()).throw(AssertionError("security block must stop archive fallback")),
    )

    result = fetcher.fetch("https://example.com/start")

    assert result.success is False
    assert result.security_blocked is True
    assert "Redirect target blocked" in result.error
    assert len(calls) == 1
    assert calls[0][1]["allow_redirects"] is False


def run_all_tests():
    """Run all tests."""
    print("=" * 70)
    print("Testing deepr scraping utilities")
    print("=" * 70)

    try:
        test_scrape_config()
        test_content_extractor()
        test_link_extractor()
        test_page_deduplicator()
        test_http_fetcher()

        print("=" * 70)
        print("ALL TESTS PASSED")
        print("=" * 70)
        return 0

    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
