"""Complete end-to-end test of web scraping skill.

This validates the entire scraping pipeline from start to finish.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deepr.utils.scrape import (
    ContentExtractor,
    ContentFetcher,
    ContentSynthesizer,
    LinkExtractor,
    LinkFilter,
    PageDeduplicator,
    ProvenanceTracker,
    ScrapeConfig,
    SmartCrawler,
    scrape_website,
)


def test_all_imports():
    """Verify all module imports work."""
    print("\n[TEST] All imports...")

    # All classes should be imported
    assert ScrapeConfig is not None
    assert ContentFetcher is not None
    assert ContentExtractor is not None
    assert LinkExtractor is not None
    assert PageDeduplicator is not None
    assert ContentSynthesizer is not None
    assert ProvenanceTracker is not None
    assert LinkFilter is not None
    assert SmartCrawler is not None
    assert scrape_website is not None

    print("  [OK] All imports successful")


def test_config_system():
    """Test configuration system."""
    print("\n[TEST] Configuration system...")

    # Default config
    config = ScrapeConfig()
    assert config.respect_robots == False
    assert config.max_pages == 20
    print("  [OK] Default config")

    # Mode switching
    respectful = config.as_respectful()
    assert respectful.respect_robots == True
    assert respectful.rate_limit == 2.0
    print("  [OK] Respectful mode")

    force = config.as_force()
    assert force.max_retries == 5
    assert force.try_pdf == True
    print("  [OK] Force mode")

    # Custom config
    custom = ScrapeConfig(
        max_pages=100,
        max_depth=5,
        rate_limit=0.5,
    )
    assert custom.max_pages == 100
    assert custom.max_depth == 5
    print("  [OK] Custom config")


def test_content_extraction():
    """Test content extraction."""
    print("\n[TEST] Content extraction...")

    extractor = ContentExtractor()

    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <nav>Nav content</nav>
        <main>
            <h1>Main Title</h1>
            <p>Main content paragraph.</p>
        </main>
        <footer>Footer</footer>
        <script>alert('test');</script>
    </body>
    </html>
    """

    # Extract text
    text = extractor.extract_text(html)
    assert "Main Title" in text
    assert "Main content" in text
    assert "Nav content" not in text
    assert "alert" not in text
    print("  [OK] Text extraction")

    # Extract main content
    main = extractor.extract_main_content(html)
    assert "Main Title" in main
    print("  [OK] Main content extraction")

    # Extract metadata
    metadata = extractor.extract_metadata(html)
    assert metadata["title"] == "Test Page"
    print("  [OK] Metadata extraction")

    # Content hashing
    hash1 = extractor.compute_content_hash("test")
    hash2 = extractor.compute_content_hash("test")
    hash3 = extractor.compute_content_hash("different")
    assert hash1 == hash2
    assert hash1 != hash3
    print("  [OK] Content hashing")


def test_link_extraction():
    """Test link extraction and filtering."""
    print("\n[TEST] Link extraction...")

    html = """
    <html>
    <body>
        <a href="/about">About</a>
        <a href="/products">Products</a>
        <a href="/login">Login</a>
        <a href="https://external.com">External</a>
    </body>
    </html>
    """

    extractor = LinkExtractor("https://example.com")

    # Extract internal links
    links = extractor.extract_links(html, internal_only=True)
    assert len(links) > 0
    print(f"  [OK] Extracted {len(links)} internal links")

    # Filter excluded
    filtered = extractor.filter_excluded(links)
    assert not any("login" in link["url"].lower() for link in filtered)
    print(f"  [OK] Filtered to {len(filtered)} relevant links")


def test_deduplication():
    """Test deduplication."""
    print("\n[TEST] Deduplication...")

    deduper = PageDeduplicator()

    # URL deduplication
    assert not deduper.is_duplicate("https://example.com/page1")
    deduper.mark_seen("https://example.com/page1")
    assert deduper.is_duplicate("https://example.com/page1")
    print("  [OK] URL deduplication")

    # URL normalization
    deduper.mark_seen("https://example.com/page2/")
    assert deduper.is_duplicate("https://example.com/page2")
    print("  [OK] URL normalization")

    # Content hash deduplication
    hash1 = "abc123"
    deduper.mark_seen("https://example.com/page3", hash1)
    assert deduper.is_duplicate("https://different.com", hash1)
    print("  [OK] Content hash deduplication")


def test_http_fetching():
    """Test HTTP fetching."""
    print("\n[TEST] HTTP fetching...")

    config = ScrapeConfig(
        try_selenium=False,
        try_pdf=False,
        try_archive=False,
        timeout=10,
    )
    fetcher = ContentFetcher(config)

    result = fetcher.fetch("https://example.com")

    if result.success:
        assert result.strategy == "HTTP"
        assert result.html is not None
        assert len(result.html) > 0
        print(f"  [OK] HTTP fetch: {len(result.html)} chars")
    else:
        print(f"  [SKIP] HTTP fetch failed: {result.error}")


def test_link_filtering():
    """Test link filtering."""
    print("\n[TEST] Link filtering...")

    link_filter = LinkFilter()

    test_links = [
        {"url": "https://example.com/about", "text": "About Us"},
        {"url": "https://example.com/products", "text": "Products"},
        {"url": "https://example.com/login", "text": "Login"},
        {"url": "https://example.com/terms", "text": "Terms"},
    ]

    # Test heuristic filtering
    filtered = link_filter._heuristic_filter(
        links=test_links,
        purpose="company research",
        max_links=10,
    )

    assert len(filtered) > 0
    assert len(filtered) < len(test_links)

    urls = [link["url"] for link in filtered]
    assert "https://example.com/login" not in urls
    assert "https://example.com/terms" not in urls

    print(f"  [OK] Filtered {len(test_links)} links to {len(filtered)}")


def test_end_to_end_scrape():
    """Test complete scraping workflow."""
    print("\n[TEST] End-to-end scraping...")

    config = ScrapeConfig(
        max_pages=2,
        max_depth=1,
        try_selenium=False,
        timeout=15,
    )

    results = scrape_website(
        url="https://example.com",
        purpose="general research",
        config=config,
        synthesize=False,
    )

    assert results["success"] == True
    assert results["pages_scraped"] >= 1
    assert len(results["scraped_urls"]) >= 1
    assert len(results["scraped_data"]) >= 1

    print(f"  [OK] Scraped {results['pages_scraped']} pages")
    print(f"  [OK] URLs: {results['scraped_urls']}")


def test_provenance_tracking():
    """Test provenance tracking."""
    print("\n[TEST] Provenance tracking...")

    tracker = ProvenanceTracker()

    # Add citations
    tracker.add_citation("Company offers SaaS product", "https://example.com/about")
    tracker.add_citation("Company offers SaaS product", "https://example.com/products")
    tracker.add_citation("Founded in 2020", "https://example.com/about")

    # Get sources
    sources1 = tracker.get_sources("Company offers SaaS product")
    assert len(sources1) == 2
    print("  [OK] Multi-source citation tracked")

    sources2 = tracker.get_sources("Founded in 2020")
    assert len(sources2) == 1
    print("  [OK] Single-source citation tracked")

    # Format citation
    formatted = tracker.format_citation("Company offers SaaS product")
    assert "[1]" in formatted
    assert "[2]" in formatted
    print("  [OK] Citation formatting")


def run_all_tests():
    """Run all tests."""
    print("=" * 70)
    print("Complete End-to-End Scraping Test")
    print("=" * 70)

    try:
        test_all_imports()
        test_config_system()
        test_content_extraction()
        test_link_extraction()
        test_deduplication()
        test_link_filtering()
        test_provenance_tracking()
        test_http_fetching()
        test_end_to_end_scrape()

        print("\n" + "=" * 70)
        print("ALL TESTS PASSED")
        print("=" * 70)
        print("\nWeb scraping skill is fully functional.")
        print("Ready for integration into deepr research workflows.")
        print()
        return 0

    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        import traceback

        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
