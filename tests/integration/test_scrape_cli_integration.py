"""Test CLI integration with scraping functionality."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deepr.utils.scrape import ScrapeConfig, scrape_website


def test_cli_scraping_workflow():
    """Test the scraping workflow that CLI would use."""
    print("\n" + "=" * 70)
    print("CLI Scraping Integration Test")
    print("=" * 70 + "\n")

    # Scrape a website (what CLI does)
    print("[TEST] Scraping example.com...")
    config = ScrapeConfig(
        max_pages=1,
        max_depth=1,
        try_selenium=False,
    )

    results = scrape_website(
        url="https://example.com",
        purpose="company research",
        config=config,
        synthesize=False,
    )

    assert results["success"] == True
    print(f"  [OK] Scraping successful: {results['pages_scraped']} pages")

    # Save to temporary file (what CLI does)
    print("[TEST] Saving scraped content to temp file...")
    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    temp_file.write("# Scraped Content from example.com\n\n")
    temp_file.write(f"**Scraped {results['pages_scraped']} pages**\n\n")

    for url, content in results["scraped_data"].items():
        temp_file.write(f"## Source: {url}\n\n")
        temp_file.write(content)
        temp_file.write("\n\n---\n\n")

    temp_file.close()
    print(f"  [OK] Saved to: {temp_file.name}")

    # Verify file was created and has content
    print("[TEST] Verifying temp file...")
    assert os.path.exists(temp_file.name)
    with open(temp_file.name, encoding="utf-8") as f:
        content = f.read()
        assert len(content) > 100
        assert "# Scraped Content" in content
        assert "example.com" in content
    print(f"  [OK] Temp file valid: {len(content)} chars")

    # Cleanup
    os.unlink(temp_file.name)
    print("  [OK] Cleanup complete")

    print("\n" + "=" * 70)
    print("CLI Integration Test PASSED")
    print("=" * 70)
    print("\nCLI command would be:")
    print('deepr research "Analyze example.com" --scrape https://example.com')
    print("\nThis would:")
    print("1. Scrape the website")
    print("2. Save content to temp file")
    print("3. Pass temp file to research command via --upload")
    print("4. Deep research analyzes scraped content + web research")
    print()


if __name__ == "__main__":
    try:
        test_cli_scraping_workflow()
        sys.exit(0)
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
