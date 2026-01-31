"""Test smart scraping with LLM-guided filtering."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from deepr.utils.scrape import scrape_website, ScrapeConfig


def test_smart_scrape():
    """Test complete smart scraping workflow."""
    print("\n" + "="*70)
    print("Smart Scraping Test (LLM-Guided)")
    print("="*70 + "\n")

    # Use a simple config for testing
    config = ScrapeConfig(
        max_pages=5,
        max_depth=1,
        try_selenium=False,
        try_pdf=False,
        try_archive=False,
        timeout=15,
    )

    # Test with example.com (simple, reliable)
    print("[TEST] Scraping example.com...")
    print("Note: example.com has no links, so this tests the basic flow\n")

    try:
        results = scrape_website(
            url="https://example.com",
            purpose="company research",
            company_name="Example Corp",
            config=config,
            synthesize=False,  # Skip synthesis for basic test
        )

        print(f"[OK] Scrape completed: {results['success']}")
        print(f"[OK] Pages scraped: {results['pages_scraped']}")
        print(f"[OK] URLs: {results['scraped_urls']}")

        assert results['success'] is True
        assert results['pages_scraped'] >= 1
        assert len(results['scraped_data']) >= 1

        print("\n[PASS] Smart scraping working\n")

    except Exception as e:
        print(f"\n[FAIL] Smart scrape failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def test_link_filter_heuristic():
    """Test link filtering with heuristic fallback."""
    print("\n" + "="*70)
    print("Link Filter Heuristic Test")
    print("="*70 + "\n")

    from deepr.utils.scrape.filter import LinkFilter

    filter = LinkFilter()

    # Test links for company research
    test_links = [
        {"url": "https://example.com/about", "text": "About Us"},
        {"url": "https://example.com/products", "text": "Products"},
        {"url": "https://example.com/login", "text": "Sign In"},
        {"url": "https://example.com/pricing", "text": "Pricing"},
        {"url": "https://example.com/terms", "text": "Terms"},
        {"url": "https://example.com/team", "text": "Our Team"},
    ]

    print("[TEST] Filtering links with heuristic...")
    filtered = filter._heuristic_filter(
        links=test_links,
        purpose="company research",
        max_links=10,
    )

    print(f"[OK] Filtered {len(test_links)} links to {len(filtered)}")

    # Should keep about, products, pricing, team
    # Should remove login, terms
    assert len(filtered) > 0
    assert len(filtered) < len(test_links)

    urls = [link['url'] for link in filtered]
    assert "https://example.com/login" not in urls
    assert "https://example.com/terms" not in urls

    print("[OK] Login and terms filtered out")

    for link in filtered:
        print(f"  Kept: {link['url']} (score: {link['relevance_score']})")

    print("\n[PASS] Heuristic filtering working\n")
    return True


def run_all_tests():
    """Run all smart scraping tests."""
    print("="*70)
    print("Testing Smart Scraping")
    print("="*70)

    try:
        if not test_link_filter_heuristic():
            return 1

        if not test_smart_scrape():
            return 1

        print("="*70)
        print("ALL SMART SCRAPING TESTS PASSED")
        print("="*70)
        return 0

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
