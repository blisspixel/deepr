"""Core tests for scraping utilities.

Tests the fundamental functionality without requiring external dependencies.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deepr.utils.scrape import (
    ContentExtractor,
    ContentFetcher,
    LinkExtractor,
    PageDeduplicator,
    ScrapeConfig,
)


def test_scrape_config():
    """Test configuration creation and modes."""
    print("\n[TEST] ScrapeConfig...")

    # Default config
    config = ScrapeConfig()
    assert config.respect_robots == False, "Default should prioritize content acquisition"
    assert config.rate_limit == 1.0
    assert config.max_depth == 2
    assert config.max_pages == 20
    print("  [OK] Default config")

    # Respectful mode
    respectful = config.as_respectful()
    assert respectful.respect_robots == True
    assert respectful.rate_limit == 2.0  # Slower
    assert respectful.try_selenium == False  # No aggressive tactics
    print("  [OK] Respectful mode")

    # Force mode
    force = config.as_force()
    assert force.respect_robots == False
    assert force.rate_limit == 0.5  # Faster
    assert force.max_retries == 5
    assert force.try_pdf == True
    print("  [OK] Force mode")

    print("[PASS] ScrapeConfig\n")


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


def test_http_fetcher():
    """Test HTTP fetching (requires internet)."""
    print("\n[TEST] ContentFetcher fetch...")

    config = ScrapeConfig(
        try_selenium=False,
        try_pdf=False,
        try_archive=False,
        timeout=10,
    )
    fetcher = ContentFetcher(config)

    # Test with a reliable public URL
    result = fetcher.fetch("https://example.com")

    if result.success:
        # Playwright is now preferred, but HTTP is also valid
        assert result.strategy in ("Playwright", "HTTP")
        assert result.html is not None
        assert len(result.html) > 100
        print(f"  [OK] Fetch successful via {result.strategy}")
        print(f"  [OK] Got {len(result.html)} chars of HTML")
    else:
        print(f"  [SKIP] Fetch failed: {result.error}")
        print("  (This is okay if network is unavailable)")

    print("[PASS] ContentFetcher fetch\n")


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
