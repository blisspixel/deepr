"""Real-world scraping test with actual website.

This test demonstrates the full scraping workflow on a real site.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deepr.utils.scrape import ScrapeConfig


def test_realworld_scrape():
    """Test scraping a real company website."""
    print("\n" + "=" * 70)
    print("Real-World Scraping Test")
    print("=" * 70 + "\n")

    # Use Python.org as test (well-structured, reliable)
    print("[TEST] Scraping python.org (small sample)...")
    print("This demonstrates the full workflow on a real site\n")

    # Conservative config for testing
    config = ScrapeConfig(
        max_pages=3,  # Just a few pages
        max_depth=1,  # Stay shallow
        try_selenium=False,
        timeout=15,
    )

    try:
        from deepr.utils.scrape import scrape_website

        results = scrape_website(
            url="https://www.python.org",
            purpose="documentation",
            company_name="Python",
            config=config,
            synthesize=False,  # Skip synthesis to save time
        )

        print("\n[RESULTS]")
        print("=" * 70)
        print(f"Success: {results['success']}")
        print(f"Pages scraped: {results['pages_scraped']}")
        print(f"Purpose: {results['purpose']}")
        print("\nScraped URLs:")
        for i, url in enumerate(results["scraped_urls"], 1):
            print(f"  {i}. {url}")

        # Show sample of scraped content
        if results["scraped_data"]:
            first_url = results["scraped_urls"][0]
            content = results["scraped_data"][first_url]
            print(f"\nSample content from {first_url}:")
            print(f"  Length: {len(content)} chars")
            print(f"  Preview: {content[:300]}...")

        print("\n" + "=" * 70)

        # Assertions
        assert results["success"] is True
        assert results["pages_scraped"] >= 1
        assert len(results["scraped_data"]) >= 1

        # Verify content is not empty
        for url, content in results["scraped_data"].items():
            assert len(content) > 100, f"Content too short for {url}"

        print("\n[PASS] Real-world scraping successful")
        print("Scraped and extracted content from actual website\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Real-world scrape failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_config_modes():
    """Test different configuration modes."""
    print("\n" + "=" * 70)
    print("Configuration Modes Test")
    print("=" * 70 + "\n")

    # Default config
    config = ScrapeConfig()
    print(f"[DEFAULT] respect_robots={config.respect_robots}, rate_limit={config.rate_limit}")
    assert config.respect_robots == False
    assert config.rate_limit == 1.0

    # Respectful mode
    respectful = config.as_respectful()
    print(f"[RESPECTFUL] respect_robots={respectful.respect_robots}, rate_limit={respectful.rate_limit}")
    assert respectful.respect_robots == True
    assert respectful.rate_limit == 2.0
    assert respectful.try_selenium == False

    # Force mode
    force = config.as_force()
    print(
        f"[FORCE] respect_robots={force.respect_robots}, rate_limit={force.rate_limit}, max_retries={force.max_retries}"
    )
    assert force.respect_robots == False
    assert force.rate_limit == 0.5
    assert force.max_retries == 5
    assert force.try_pdf == True

    print("\n[PASS] All configuration modes working\n")
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("Real-World Scraping Tests")
    print("=" * 70)

    try:
        if not test_config_modes():
            sys.exit(1)

        if not test_realworld_scrape():
            sys.exit(1)

        print("=" * 70)
        print("ALL REAL-WORLD TESTS PASSED")
        print("=" * 70)
        print("\nWeb scraping skill is working and tested.")
        print("Ready for integration into deepr research workflows.\n")
        sys.exit(0)

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
