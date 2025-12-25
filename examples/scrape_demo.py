"""Demo script showing how to use deepr's web scraping skill.

This demonstrates the different ways to scrape websites for research purposes.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from deepr.utils.scrape import (
    scrape_website,
    scrape_for_company_research,
    scrape_for_documentation,
    ScrapeConfig,
)


def demo_basic_scrape():
    """Basic scraping example."""
    print("\n" + "="*70)
    print("Demo 1: Basic Website Scraping")
    print("="*70 + "\n")

    # Scrape a simple website
    results = scrape_website(
        url="https://example.com",
        purpose="general research",
        synthesize=False,  # Don't synthesize for this simple demo
    )

    print(f"Success: {results['success']}")
    print(f"Pages scraped: {results['pages_scraped']}")
    print(f"URLs: {results['scraped_urls']}")
    print(f"Content length: {len(results['scraped_data']['https://example.com'])} chars")


def demo_company_research():
    """Company research example."""
    print("\n" + "="*70)
    print("Demo 2: Company Research (using scrape_website)")
    print("="*70 + "\n")

    config = ScrapeConfig(
        max_pages=5,
        max_depth=2,
        try_selenium=False,  # HTTP only for demo
    )

    results = scrape_website(
        url="https://www.python.org",
        purpose="company research",
        company_name="Python Software Foundation",
        config=config,
        synthesize=False,  # Skip synthesis for faster demo
    )

    print(f"Success: {results['success']}")
    print(f"Pages scraped: {results['pages_scraped']}")
    print(f"\nScraped URLs:")
    for i, url in enumerate(results['scraped_urls'], 1):
        print(f"  {i}. {url}")


def demo_documentation_scraping():
    """Documentation scraping example."""
    print("\n" + "="*70)
    print("Demo 3: Documentation Scraping (using scrape_website)")
    print("="*70 + "\n")

    config = ScrapeConfig(
        max_pages=3,
        max_depth=1,
        try_selenium=False,
    )

    results = scrape_website(
        url="https://www.python.org/doc/",
        purpose="documentation",
        config=config,
        synthesize=False,
    )

    print(f"Success: {results['success']}")
    print(f"Pages scraped: {results['pages_scraped']}")

    if results['scraped_data']:
        first_url = list(results['scraped_data'].keys())[0]
        content = results['scraped_data'][first_url]
        print(f"\nSample content from {first_url}:")
        print(f"  Length: {len(content)} chars")
        print(f"  Preview: {content[:200]}...")


def demo_configuration_modes():
    """Show different configuration modes."""
    print("\n" + "="*70)
    print("Demo 4: Configuration Modes")
    print("="*70 + "\n")

    # Default mode (aggressive, for research)
    default_config = ScrapeConfig()
    print("[DEFAULT MODE]")
    print(f"  respect_robots: {default_config.respect_robots}")
    print(f"  rate_limit: {default_config.rate_limit}s")
    print(f"  max_pages: {default_config.max_pages}")
    print(f"  try_selenium: {default_config.try_selenium}")

    # Respectful mode (polite, follows robots.txt)
    respectful_config = default_config.as_respectful()
    print("\n[RESPECTFUL MODE]")
    print(f"  respect_robots: {respectful_config.respect_robots}")
    print(f"  rate_limit: {respectful_config.rate_limit}s")
    print(f"  try_selenium: {respectful_config.try_selenium}")

    # Force mode (maximum effort to get content)
    force_config = default_config.as_force()
    print("\n[FORCE MODE]")
    print(f"  respect_robots: {force_config.respect_robots}")
    print(f"  rate_limit: {force_config.rate_limit}s")
    print(f"  max_retries: {force_config.max_retries}")
    print(f"  try_pdf: {force_config.try_pdf}")
    print(f"  try_archive: {force_config.try_archive}")


def main():
    """Run all demos."""
    print("\n")
    print("="*70)
    print("deepr Web Scraping Skill - Demonstration")
    print("="*70)

    try:
        demo_basic_scrape()
        demo_company_research()
        demo_documentation_scraping()
        demo_configuration_modes()

        print("\n" + "="*70)
        print("All demos completed successfully")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\nDemo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
