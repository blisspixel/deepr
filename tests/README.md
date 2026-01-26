# Deepr Test Suite

Comprehensive testing strategy with unit tests, integration tests, and E2E tests.

## Quick Start

### Expert Creation Testing (NEW)
Test expert creation with minimal cost (~$0.004):

```bash
# Windows
tests\test_keyboards_cli.bat

# Linux/Mac  
./tests/test_keyboards_cli.sh

# Validate learning
python tests/validate_expert_learning.py "Keyboards Test"
```

See [TEST_EXPERT_CREATION.md](TEST_EXPERT_CREATION.md) and [TESTING_SUMMARY.md](TESTING_SUMMARY.md) for details.

## Test Philosophy

After experiencing 4 failed API submissions due to untested code (Oct 30, 2025), we implemented a three-layer testing strategy:

1. **Unit Tests** - Fast, free, validate parameters with mocks
2. **Integration Tests** - Real API calls, validate contracts, use Deepr to improve Deepr
3. **E2E Tests** - Full workflows, validate user experience

**Key Insight:** Unit tests tell you if code runs. Integration tests tell you if it works.

## Test Organization

```
tests/
├── unit/                          # Unit tests (fast, free, always run)
│   ├── test_providers/
│   │   ├── test_openai_tool_validation.py    # Parameter validation
│   │   ├── test_gemini_provider.py           # Gemini comprehensive
│   │   └── test_openai_provider.py           # OpenAI basic
│   ├── test_queue/                           # Queue operations (95% coverage)
│   ├── test_storage/                         # Storage operations (85% coverage)
│   └── test_costs.py                         # Cost calculations (93% coverage)
│
├── integration/                   # Integration tests (real APIs, costs money)
│   ├── test_research_modes_comprehensive.py  # All 4 modes + dogfooding
│   ├── test_file_upload_api.py              # File upload workflows
│   ├── test_all_providers.py                # Provider comparison
│   └── test_cli_commands.py                 # CLI integration
│
├── test_e2e_cheap.py             # E2E tests (expensive, run rarely)
└── data/
    └── research_outputs/          # Saved research for review
```

## Running Tests

### Fast Tests (Unit Only - Free)

```bash
# Run all unit tests
pytest -m unit

# Run with coverage
pytest -m unit --cov=deepr --cov-report=html

# Quick smoke test
pytest -m unit --maxfail=1
```

### Integration Tests (Costs Money)

```bash
# Run cheap integration tests (~$1-2)
pytest -m "integration and not expensive"

# Run specific research mode tests (~$5-10)
pytest -m research_modes

# Run file upload tests (~$1-2)
pytest -m file_upload

# Run all integration tests (~$10-20)
pytest -m integration
```

### E2E Tests (Expensive)

```bash
# Run all E2E tests (~$20-50)
pytest -m e2e

# Run everything (unit + integration + e2e)
pytest
```

### Provider-Specific Tests

```bash
# Test only OpenAI
pytest -k "openai"

# Test only Gemini
pytest -k "gemini"

# Test all providers
pytest -k "provider"
```

## Test Markers

| Marker | Purpose | Cost | When to Run |
|--------|---------|------|-------------|
| `unit` | Unit tests, no API calls | $0 | Every commit |
| `integration` | Real API calls, cheap queries | $0.10-1 | Before PR |
| `e2e` | Full workflows | $1-10 | Before release |
| `requires_api` | Needs API key | Varies | Manual/CI |
| `file_upload` | Tests file upload | ~$1 | After file changes |
| `research_modes` | Tests all 4 modes | ~$5-10 | Weekly |
| `expensive` | Costs >$1 | >$1 | Sparingly |
| `slow` | Takes >1 second | Varies | As needed |

## Research Modes Testing

We test all 4 research modes with OpenAI (full capability), and limited modes for Gemini/Grok:

### OpenAI (Full Coverage)

1. **Focus Mode** (`test_openai_focus_mode_self_improvement`)
   - Quick research queries
   - Example: Research Python CLI best practices
   - Cost: ~$0.50-1.00
   - Duration: 5-10 min

2. **Documentation Mode** (`test_openai_docs_mode_api_research`)
   - Technical API documentation
   - Example: Research OpenAI's own API to validate our usage
   - Cost: ~$0.50-1.00
   - Duration: 5-10 min

3. **Project Mode** (`test_openai_project_mode_multi_phase`)
   - Multi-phase adaptive research
   - Example: Analyze Deepr's testing strategy (dogfooding)
   - Cost: ~$2-5
   - Duration: 10-20 min

4. **Team Mode** (`test_openai_team_mode_diverse_perspectives`)
   - Multiple perspectives synthesized
   - Example: Strategic decisions with diverse viewpoints
   - Cost: ~$3-8
   - Duration: 15-30 min

### Gemini (Focus + Docs)

- Focus mode: Basic capability check
- Docs mode: API documentation research
- No multi-phase or team modes (not supported)

### Grok (Focus Only)

- Focus mode: Basic capability check
- Limited deep research capabilities

## Dogfooding: Using Deepr to Improve Deepr

Our integration tests double as a learning feedback loop:

**Examples:**
- `test_openai_focus_mode_self_improvement` - Research Python CLI best practices
- `test_openai_docs_mode_api_research` - Research OpenAI API to validate our implementation
- `test_openai_project_mode_multi_phase` - Research testing strategy improvements
- `test_provider_comparison_same_query` - Compare providers on same question

**Benefits:**
1. Validates research quality (if Deepr can't improve Deepr, how can it help you?)
2. Generates actionable insights saved to `tests/data/research_outputs/`
3. Tests real-world use cases, not toy examples
4. Creates feedback loop for continuous improvement

**Output Location:** All research outputs are saved to `tests/data/research_outputs/` for review.

## Cost Management

### Monthly Testing Budget

- Unit tests: $0 (no API calls)
- Integration tests (CI): ~$10/month
- Integration tests (manual): ~$10/month
- E2E tests (releases): ~$20/month
- **Total: ~$40/month**

### Cost Tracking

Each test documents its expected cost in the docstring:

```python
@pytest.mark.integration
async def test_something():
    """Test description.

    Cost: ~$0.50
    Duration: 5 minutes
    """
```

### Reducing Costs

1. Run unit tests locally (free)
2. Run integration tests only when needed
3. Use `pytest -m "not expensive"` to skip high-cost tests
4. Run expensive tests only before releases

## CI/CD Integration

### Pre-Commit (Local)

```bash
# .git/hooks/pre-commit
pytest -m unit --tb=short --maxfail=3
```

### Pull Request (GitHub Actions)

```yaml
# .github/workflows/pr-tests.yml
- name: Run unit tests
  run: pytest -m unit --cov=deepr --cov-fail-under=70

# Only on main branch
- name: Run cheap integration tests
  if: github.ref == 'refs/heads/main'
  run: pytest -m "integration and not expensive"
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### Release (Before Deploy)

```yaml
# .github/workflows/release.yml
- name: Run all tests
  run: pytest --maxfail=5
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

## Writing New Tests

### Unit Test Template

```python
@pytest.mark.asyncio
async def test_something():
    """Test description."""
    provider = OpenAIProvider(api_key="test")

    with patch.object(provider.client.responses, "create") as mock:
        mock.return_value = MagicMock()

        await provider.submit_research(request)

        # KEY: Validate actual parameters
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["tools"][0] == expected_format
```

### Integration Test Template

```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_something():
    """Test description.

    Cost: ~$0.50
    Duration: 5 minutes
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("API key not set")

    provider = OpenAIProvider()  # Real provider

    request = ResearchRequest(
        prompt="Test query",
        model="o4-mini-deep-research",
        tools=[ToolConfig(type="web_search_preview")],
        background=True
    )

    job_id = await provider.submit_research(request)
    # Poll for completion and validate
```

## Test Coverage Goals

| Module | Current | Target | Status |
|--------|---------|--------|--------|
| Providers | 51% | 70% | In Progress |
| Queue | 95% | 90% | Good |
| Storage | 61% | 80% | Needs Work |
| CLI | 0% | 50% | Not Started |
| Core | 27% | 60% | Needs Work |
| Overall | 14% | 70% | In Progress |

## Best Practices

### 1. Validate Parameters, Not Just Calls

**Bad:**
```python
mock_api.assert_called_once()  # Just checks it was called
```

**Good:**
```python
call_kwargs = mock_api.call_args.kwargs
assert "container" not in call_kwargs["tools"][0]  # Validates actual parameters
```

### 2. Use Real Queries in Integration Tests

**Bad:** "Test query 123"

**Good:** "What are the latest Python CLI best practices in 2025?"

**Why:** Real queries validate actual use cases and provide learning feedback.

### 3. Save Research Outputs

```python
output_file = Path("tests/data/research_outputs/focus_result.md")
output_file.write_text(response_text)
```

This creates a corpus of research we can review and learn from.

### 4. Document Cost and Duration

Always include cost and duration estimates in test docstrings.

### 5. Create Regression Tests

When you fix a bug, add a test that would have caught it:

```python
class TestToolParameterRegressions:
    def test_regression_oct_30_2025_container_bug():
        """Regression: web_search_preview should NOT have container.

        Bug discovered: Oct 30, 2025 (4 failed submissions)
        """
        # Test implementation
```

## Troubleshooting

### Tests Fail with "API key not set"

Set environment variables:
```bash
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="..."
export GROK_API_KEY="..."
```

Or create `.env` file:
```bash
cp .env.example .env
# Edit .env with your keys
```

### Tests Time Out

Increase timeout in test:
```python
max_wait = 600  # 10 minutes
```

Or skip slow tests:
```bash
pytest -m "not slow"
```

### Tests Cost Too Much

Run only cheap tests:
```bash
pytest -m "integration and not expensive"
```

Or run unit tests only:
```bash
pytest -m unit
```

### Coverage Too Low

Run with coverage report:
```bash
pytest --cov=deepr --cov-report=html
open htmlcov/index.html  # View detailed report
```

## Related Documentation

- [docs/TESTING_STRATEGY.md](../docs/TESTING_STRATEGY.md) - Comprehensive testing philosophy
- [docs/TEST_COVERAGE_IMPROVEMENT_PLAN.md](../docs/TEST_COVERAGE_IMPROVEMENT_PLAN.md) - Roadmap to 70% coverage
- [docs/BUGFIX_CONTAINER_PARAMETER.md](../docs/BUGFIX_CONTAINER_PARAMETER.md) - The bug that motivated this

## Questions?

See the main [README.md](../README.md) or open an issue.
