"""Unit tests for smart scraping helpers."""

from deepr.utils.scrape import ScrapeConfig
from deepr.utils.scrape.filter import LinkFilter
from deepr.utils.scrape.scraper import scrape_website


def test_smart_scrape_returns_structured_result(monkeypatch):
    """scrape_website should return a stable, structured payload."""

    class _StubCrawler:
        def __init__(self, **_kwargs):
            pass

        def crawl(self, **_kwargs):
            return {
                "https://example.com": {
                    "title": "Example Domain",
                    "content": "Example content",
                    "links": [],
                }
            }

    monkeypatch.setattr("deepr.utils.scrape.scraper.SmartCrawler", _StubCrawler)

    config = ScrapeConfig(max_pages=5, max_depth=1, try_selenium=False, try_pdf=False, try_archive=False, timeout=15)
    results = scrape_website(
        url="https://example.com",
        purpose="company research",
        company_name="Example Corp",
        config=config,
        synthesize=False,
    )

    assert results["success"] is True
    assert results["pages_scraped"] == 1
    assert results["scraped_urls"] == ["https://example.com"]
    assert "scraped_data" in results
    assert results["company_name"] == "Example Corp"


def test_link_filter_heuristic():
    """Heuristic filter should keep relevant links and drop obvious noise."""
    link_filter = LinkFilter()

    test_links = [
        {"url": "https://example.com/about", "text": "About Us"},
        {"url": "https://example.com/products", "text": "Products"},
        {"url": "https://example.com/login", "text": "Sign In"},
        {"url": "https://example.com/pricing", "text": "Pricing"},
        {"url": "https://example.com/terms", "text": "Terms"},
        {"url": "https://example.com/team", "text": "Our Team"},
    ]

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

    for link in filtered:
        assert "relevance_score" in link


def test_link_filter_short_score_list_falls_back_instead_of_dropping_links():
    """A model score list shorter than the links must not silently drop the unscored links."""
    links = [{"url": f"https://example.com/page{index}", "text": f"Page {index}"} for index in range(4)]
    link_filter = LinkFilter(llm_client=lambda prompt: "[9, 8]")
    heuristic = link_filter._heuristic_filter(links=links, purpose="company research", max_links=3)

    filtered = link_filter.filter_links(links, "company research", max_links=3)

    assert filtered == heuristic


def test_scrape_for_company_research_sanitizes_path(tmp_path, monkeypatch):
    from deepr.utils.scrape.scraper import scrape_for_company_research

    class _StubCrawler:
        def __init__(self, **_kwargs):
            pass

        def crawl(self, **_kwargs):
            return {
                "https://example.com": {
                    "title": "Example",
                    "content": "Example content",
                    "links": [],
                }
            }

    monkeypatch.setattr("deepr.utils.scrape.scraper.SmartCrawler", _StubCrawler)
    monkeypatch.setattr(
        "deepr.utils.scrape.scraper.ContentSynthesizer.synthesize",
        lambda *args, **kwargs: {"success": True, "insights": "dummy insights"},
    )

    result = scrape_for_company_research(
        company_url="https://example.com",
        company_name="../../evil_corp",
        save_dir=str(tmp_path),
    )
    assert result["pages_scraped"] == 1
    created_files = list(tmp_path.glob("*.json"))
    assert len(created_files) == 1
    assert ".." not in created_files[0].name
    assert "evil_corp" in created_files[0].name


def test_content_synthesizer_combines_with_boundary_markers():
    from deepr.utils.scrape.synthesizer import ContentSynthesizer

    synthesizer = ContentSynthesizer()
    combined = synthesizer._combine_content({"https://example.com": "Some scraped text"})
    assert "DEEPR_UNTRUSTED_CONTENT_BEGIN" in combined
    assert "DEEPR_UNTRUSTED_CONTENT_END" in combined
