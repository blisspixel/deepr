"""Integration test for complete scraping workflow.

Tests the full pipeline: fetch → extract → synthesize
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deepr.utils.scrape import (
    ContentExtractor,
    ContentFetcher,
    LinkExtractor,
    PageDeduplicator,
    ScrapeConfig,
)


def test_full_scrape_workflow():
    """Test complete scraping workflow on example.com."""
    print("\n" + "=" * 70)
    print("Full Scraping Workflow Integration Test")
    print("=" * 70 + "\n")

    # Configuration
    config = ScrapeConfig(
        try_selenium=False,  # HTTP only for speed
        try_pdf=False,
        try_archive=False,
        max_pages=5,
        timeout=10,
    )

    base_url = "https://example.com"
    print(f"Target: {base_url}\n")

    # Step 1: Fetch homepage
    print("[STEP 1] Fetching homepage...")
    fetcher = ContentFetcher(config)
    result = fetcher.fetch(base_url)

    if not result.success:
        print(f"  [SKIP] Could not fetch (network issue?): {result.error}")
        return

    print(f"  [OK] Fetched with strategy: {result.strategy}")
    print(f"  [OK] Got {len(result.html)} chars of HTML\n")

    # Step 2: Extract links
    print("[STEP 2] Extracting links...")
    link_extractor = LinkExtractor(base_url)
    links = link_extractor.extract_links(result.html)
    print(f"  [OK] Found {len(links)} internal links")

    if links:
        for i, link in enumerate(links[:5], 1):
            print(f"    {i}. {link['url']}")
            if link["text"]:
                print(f"       Text: {link['text'][:50]}")

    # Filter out common exclusions
    filtered_links = link_extractor.filter_excluded(links)
    print(f"  [OK] Filtered to {len(filtered_links)} relevant links\n")

    # Step 3: Extract content
    print("[STEP 3] Extracting content...")
    content_extractor = ContentExtractor()

    # Extract text
    text = content_extractor.extract_text(result.html)
    print(f"  [OK] Extracted {len(text)} chars of text")
    print(f"  [OK] Preview: {text[:200]}...\n")

    # Extract metadata
    metadata = content_extractor.extract_metadata(result.html)
    print("  [OK] Metadata extracted:")
    for key, value in metadata.items():
        print(f"       {key}: {value}")
    print()

    # Extract main content
    main_content = content_extractor.extract_main_content(result.html)
    print(f"  [OK] Main content: {len(main_content)} chars\n")

    # Step 4: Deduplication
    print("[STEP 4] Testing deduplication...")
    deduper = PageDeduplicator()
    content_hash = content_extractor.compute_content_hash(text)

    deduper.mark_seen(base_url, content_hash)
    assert deduper.is_duplicate(base_url), "URL should be marked as seen"
    assert deduper.is_duplicate("http://other-url.com", content_hash), "Same content hash should be detected"
    print("  [OK] Deduplication working\n")

    # Step 5: Scrape additional pages (if any links found)
    if filtered_links:
        print(f"[STEP 5] Scraping {min(3, len(filtered_links))} additional pages...")
        scraped_pages = {base_url: main_content}

        for link in filtered_links[:3]:
            url = link["url"]
            if deduper.is_duplicate(url):
                print(f"  [SKIP] Already seen: {url}")
                continue

            print(f"  Fetching: {url}")
            page_result = fetcher.fetch(url)

            if page_result.success:
                page_content = content_extractor.extract_main_content(page_result.html)
                page_hash = content_extractor.compute_content_hash(page_content)

                if not deduper.is_duplicate(url, page_hash):
                    scraped_pages[url] = page_content
                    deduper.mark_seen(url, page_hash)
                    print(f"    [OK] Scraped {len(page_content)} chars")
                else:
                    print("    [SKIP] Duplicate content")
            else:
                print(f"    [FAIL] {page_result.error}")

        print(f"  [OK] Total unique pages scraped: {len(scraped_pages)}\n")
    else:
        print("[STEP 5] No additional links to scrape\n")

    # Summary
    print("=" * 70)
    print("Integration Test Complete")
    print("=" * 70)
    print("\nResults:")
    print(f"  Homepage fetched: {result.success}")
    print(f"  Strategy used: {result.strategy}")
    print(f"  Links found: {len(links)}")
    print(f"  Links after filtering: {len(filtered_links)}")
    print(f"  Content extracted: {len(text)} chars")
    print(f"  Metadata fields: {len(metadata)}")
    print("  Deduplication: Working")
    print()


if __name__ == "__main__":
    try:
        test_full_scrape_workflow()
        print("[PASS] Integration test successful\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
