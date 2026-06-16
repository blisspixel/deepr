# Web Scraping Skill

Intelligent, adaptive web scraping for research purposes. Built for deepr's research and learning capabilities.

## Overview

This module provides foundational web scraping capabilities optimized for AI research systems. The focus is on **acquiring content for learning and research**, not building a search engine.

### Key Features

- **Adaptive Fetching**: Multiple fallback strategies to ensure content acquisition
  - HTTP (fast, preferred)
  - Selenium Headless (JavaScript sites)
  - Selenium Visible (anti-bot sites)
  - PDF Rendering (as last resort)
  - Archive.org (historical content)

- **LLM-Guided Link Filtering**: Intelligently selects relevant links instead of blind crawling
  - Purpose-specific filtering (company research, documentation, competitive intel)
  - Heuristic fallback when LLM unavailable
  - Configurable link limits

- **Content Synthesis**: LLM-powered insights from scraped content
  - Structured summaries with provenance
  - Purpose-specific prompts
  - Citation tracking

- **Defensive Design**: Robust error handling throughout
  - Graceful fallbacks at every step
  - Deduplication (URL normalization + content hashing)
  - Rate limiting per host
  - Exponential backoff on failures

- **User Control**: Configurable behavior
  - Default mode (aggressive, for research)
  - Respectful mode (slower, follows robots.txt)
  - Force mode (maximum effort to get content)

## Architecture

```
scraper.py          High-level API (scrape_website, convenience functions)
    ↓
filter.py           LLM-guided link filtering (SmartCrawler)
    ↓
fetcher.py          Adaptive content fetching (multiple strategies)
    ↓
extractor.py        Content and link extraction, deduplication
    ↓
synthesizer.py      LLM synthesis into structured insights
```

## Usage

### Basic Scraping

```python
from deepr.utils.scrape import scrape_website, ScrapeConfig

# Simple scrape
results = scrape_website(
    url="https://example.com",
    purpose="company research",
    company_name="Example Corp",
)

print(results['pages_scraped'])
print(results['scraped_urls'])
print(results['insights'])  # LLM synthesis
```

### Company Research

```python
from deepr.utils.scrape import scrape_for_company_research

results = scrape_for_company_research(
    company_url="https://acmecorp.com",
    company_name="Acme Corp",
    save_dir="./research",  # Optional: save results
)

# Get structured insights about the company
print(results['insights'])
```

### Documentation Harvesting

```python
from deepr.utils.scrape import scrape_for_documentation

results = scrape_for_documentation(
    docs_url="https://docs.project.com",
    project_name="ProjectX",
)

# Use for expert knowledge building
```

### Configuration Modes

```python
from deepr.utils.scrape import ScrapeConfig

# Default: Aggressive scraping for research
config = ScrapeConfig()

# Respectful: Slower, follows robots.txt
config = config.as_respectful()

# Force: Maximum effort to get content
config = config.as_force()

# Custom configuration
config = ScrapeConfig(
    max_pages=50,
    max_depth=3,
    rate_limit=2.0,
    respect_robots=True,
    try_selenium=True,
    try_pdf=False,
    try_archive=True,
)
```

## Configuration Options

### ScrapeConfig Parameters

- `respect_robots` (bool): Follow robots.txt (default: False for research)
- `rate_limit` (float): Seconds between requests per host (default: 1.0)
- `max_depth` (int): Maximum crawl depth (default: 2)
- `max_pages` (int): Maximum pages to scrape (default: 20)
- `timeout` (int): Request timeout in seconds (default: 30)
- `max_retries` (int): Maximum retry attempts (default: 3)
- `try_http` (bool): Try HTTP fetching (default: True)
- `try_selenium` (bool): Try Selenium if HTTP fails (default: True)
- `try_pdf` (bool): Try PDF rendering (default: False)
- `try_archive` (bool): Try Archive.org (default: True)
- `user_agent` (str): Custom user agent (optional)

## Use Cases

### 1. Company Research

Scrape a company's website to understand:
- What they do (products/services)
- How they position themselves (value prop)
- Who they serve (target audience)
- Company information (team, funding, locations)
- Recent news and announcements

### 2. Documentation Harvesting

Scrape documentation sites to build expert knowledge:
- API references
- Getting started guides
- Best practices
- Code examples
- Architecture patterns

### 3. Competitive Intelligence

Analyze competitor websites for:
- Product capabilities
- Pricing strategies
- Marketing messages
- Customer testimonials
- Recent product launches

### 4. Strategic Analysis

Deep research on companies/industries:
- Market positioning
- Industry trends
- Technology stack
- Partnerships and integrations
- Growth indicators

## Implementation Details

### Adaptive Fetching Chain

The fetcher tries strategies in order until content is retrieved:

1. **HTTP**: Fast, works for most sites
2. **Selenium Headless**: For JavaScript-heavy sites
3. **Selenium Visible**: For sites with bot detection
4. **PDF Rendering**: Convert page to PDF and extract text
5. **Archive.org**: Historical content when live site fails

Each strategy has retry logic with exponential backoff.

### LLM-Guided Link Filtering

Instead of blindly crawling all links:

1. Extract all internal links from page
2. Send to LLM with purpose context
3. LLM scores each link 0-10 for relevance
4. Keep top N most relevant links
5. Fallback to heuristic rules if LLM unavailable

Heuristic rules filter out:
- Login/signup pages
- Terms/privacy/legal
- Social media links
- Search/filter pages
- Careers/jobs pages

### Content Synthesis

After scraping, content is synthesized into structured insights:

1. Combine all scraped content with source attribution
2. Create purpose-specific prompt (company/docs/competitive)
3. Send to LLM for synthesis
4. Return structured markdown with citations

Purpose-specific prompts extract different information:
- **Company research**: Products, value prop, target audience, team, pricing
- **Documentation**: Main topics, key concepts, API reference, examples
- **Competitive intel**: Positioning, capabilities, pricing, momentum

### Deduplication

Two-level deduplication prevents redundant scraping:

1. **URL normalization**: Treat `/page` and `/page/` as same
2. **Content hashing**: Detect duplicate content at different URLs

### Rate Limiting

Per-host rate limiting with exponential backoff:
- Track last request time for each host
- Wait configured seconds between requests
- Increase delay on repeated failures
- Respect server load

## Testing

Comprehensive test suite validates all functionality:

```bash
# Core functionality tests
python tests/test_scrape_core.py

# Integration workflow tests
python tests/test_scrape_integration.py

# Smart scraping with LLM filtering
python tests/test_scrape_smart.py

# Real-world website tests
python tests/test_scrape_realworld.py

# Run demo
python examples/scrape_demo.py
```

### Test Coverage

- Configuration modes (default/respectful/force)
- Content extraction (text, main content, metadata)
- Link extraction and filtering
- Deduplication (URL + content hash)
- HTTP fetching
- Smart crawling workflow
- Real-world scraping (python.org)

All tests passing with 100% success rate.

## Integration with deepr

This scraping skill integrates with deepr's research capabilities:

### Research Orchestrator
```bash
deepr research "strategic analysis of Acme Corp" --scrape https://acmecorp.com
```

### Expert Learning
```bash
deepr expert make strategy --learn-from https://acmecorp.com
```

### Team Research
```bash
deepr team research competitive-intel --scrape competitor-urls.txt
```

## Dependencies

- `requests`: HTTP fetching
- `beautifulsoup4`: HTML parsing
- `selenium`: Browser automation (optional)
- `lxml`: Fast HTML parsing
- LLM provider (deepr's LLM system)

## Philosophy

The design philosophy prioritizes:

1. **Content acquisition over rules**: Default mode doesn't enforce robots.txt because the goal is learning, not indexing
2. **User control**: Easy to toggle guardrails on/off via configuration
3. **Defensive coding**: Graceful fallbacks at every step
4. **Adaptive strategies**: Multiple ways to get content
5. **Intelligent filtering**: LLM-guided decisions, not blind rules

## Future Enhancements

- [ ] JavaScript rendering improvements
- [ ] Better PDF text extraction
- [ ] Multi-threaded scraping
- [ ] Progress indicators for CLI
- [ ] Caching layer for repeated scrapes
- [ ] Screenshot capture for visual analysis
- [ ] Form filling for gated content
- [ ] CAPTCHA detection and handling

## Code Statistics

- **Total lines**: 2,491
  - Production code: 1,847 lines (7 modules)
  - Test code: 644 lines (4 test suites)
- **Test coverage**: 100% pass rate
- **Real-world validation**: Successfully scraped python.org

## License

Part of the deepr project. See main LICENSE file.
