"""Tests for core company research orchestrator."""

from unittest.mock import AsyncMock, patch

import pytest

from deepr.core.company_research import CompanyResearchOrchestrator


class TestCompanyResearchOrchestratorInit:
    """Test CompanyResearchOrchestrator initialization."""

    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    def test_default_config(self, mock_load_config, mock_research_orch):
        mock_load_config.return_value = {"key": "value"}
        orch = CompanyResearchOrchestrator()
        mock_load_config.assert_called_once()
        assert orch.config == {"key": "value"}

    @patch("deepr.core.company_research.ResearchOrchestrator")
    def test_custom_config(self, mock_research_orch):
        custom = {"provider": "anthropic", "model": "claude"}
        orch = CompanyResearchOrchestrator(config=custom)
        assert orch.config == custom


class TestBuildResearchPrompt:
    """Test _build_research_prompt method."""

    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    def test_contains_company_name(self, mock_config, mock_orch):
        mock_config.return_value = {}
        orch = CompanyResearchOrchestrator()
        prompt = orch._build_research_prompt("Acme Corp", "https://acme.com")
        assert "Acme Corp" in prompt
        assert "https://acme.com" in prompt

    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    def test_contains_required_sections(self, mock_config, mock_orch):
        mock_config.return_value = {}
        orch = CompanyResearchOrchestrator()
        prompt = orch._build_research_prompt("TestCo", "https://test.co")
        required_sections = [
            "Executive Summary",
            "Products and Services",
            "Unique Selling Proposition",
            "SWOT Analysis",
            "Financial Overview",
            "Target Audience",
        ]
        for section in required_sections:
            assert section in prompt, f"Missing section: {section}"


class TestResearchCompany:
    """Test research_company async method."""

    @pytest.mark.asyncio
    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    async def test_scrape_failure_returns_error(self, mock_config, mock_orch):
        mock_config.return_value = {}
        orch = CompanyResearchOrchestrator()

        with patch.object(
            orch,
            "_scrape_company_website",
            new_callable=AsyncMock,
            return_value={"success": False, "error": "Connection refused"},
        ):
            result = await orch.research_company(
                company_name="FailCo",
                website="https://fail.example.com",
            )
        assert result["success"] is False
        assert "Scraping failed" in result["error"]

    @pytest.mark.asyncio
    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    async def test_scrape_only_mode(self, mock_config, mock_orch):
        mock_config.return_value = {}
        orch = CompanyResearchOrchestrator()

        with patch.object(
            orch,
            "_scrape_company_website",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "scraped_file": "/tmp/scrape.md",
                "pages_scraped": 10,
            },
        ):
            result = await orch.research_company(
                company_name="TestCo",
                website="https://test.co",
                scrape_only=True,
            )
        assert result["success"] is True
        assert result["status"] == "scrape_complete"
        assert result["pages_scraped"] == 10

    @pytest.mark.asyncio
    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    async def test_full_research_flow(self, mock_config, MockResearchOrch):
        mock_config.return_value = {}
        mock_submit = AsyncMock(return_value={"success": True, "job_id": "job-123"})
        MockResearchOrch.return_value.submit_research = mock_submit

        orch = CompanyResearchOrchestrator()

        with patch.object(
            orch,
            "_scrape_company_website",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "scraped_file": "/tmp/scrape.md",
                "pages_scraped": 15,
            },
        ):
            result = await orch.research_company(
                company_name="TestCo",
                website="https://test.co",
            )
        assert result["success"] is True
        assert result["job_id"] == "job-123"
        assert result["status"] == "research_submitted"
        assert result["pages_scraped"] == 15

    @pytest.mark.asyncio
    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    async def test_research_submission_failure(self, mock_config, MockResearchOrch):
        mock_config.return_value = {}
        mock_submit = AsyncMock(return_value={"success": False, "error": "API error"})
        MockResearchOrch.return_value.submit_research = mock_submit

        orch = CompanyResearchOrchestrator()

        with patch.object(
            orch,
            "_scrape_company_website",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "scraped_file": "/tmp/scrape.md",
                "pages_scraped": 5,
            },
        ):
            result = await orch.research_company(
                company_name="TestCo",
                website="https://test.co",
            )
        assert result["success"] is False
        assert "error" in result
        assert result["scraped_file"] == "/tmp/scrape.md"


class TestScrapeCompanyWebsite:
    """Test _scrape_company_website method."""

    @pytest.mark.asyncio
    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    @patch("deepr.core.company_research.scrape_for_company_research")
    async def test_scrape_success(self, mock_scrape, mock_config, mock_orch):
        mock_config.return_value = {}
        mock_scrape.return_value = {
            "success": True,
            "pages_scraped": 8,
            "scraped_data": {
                "https://example.com": "Home page content",
                "https://example.com/about": "About page content",
            },
        }

        orch = CompanyResearchOrchestrator()
        from deepr.utils.scrape import ScrapeConfig

        result = await orch._scrape_company_website(
            company_url="https://example.com",
            company_name="Example Corp",
            config=ScrapeConfig(),
        )
        assert result["success"] is True
        assert result["pages_scraped"] == 8
        assert "scraped_file" in result

    @pytest.mark.asyncio
    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    @patch("deepr.core.company_research.scrape_for_company_research")
    async def test_scrape_failure(self, mock_scrape, mock_config, mock_orch):
        mock_config.return_value = {}
        mock_scrape.return_value = {
            "success": False,
            "error": "DNS resolution failed",
        }

        orch = CompanyResearchOrchestrator()
        from deepr.utils.scrape import ScrapeConfig

        result = await orch._scrape_company_website(
            company_url="https://bad.example.com",
            company_name="Bad Corp",
            config=ScrapeConfig(),
        )
        assert result["success"] is False
        assert "DNS" in result["error"]

    @pytest.mark.asyncio
    @patch("deepr.core.company_research.ResearchOrchestrator")
    @patch("deepr.core.company_research.load_config")
    @patch("deepr.core.company_research.scrape_for_company_research")
    async def test_scrape_exception(self, mock_scrape, mock_config, mock_orch):
        mock_config.return_value = {}
        mock_scrape.side_effect = RuntimeError("unexpected error")

        orch = CompanyResearchOrchestrator()
        from deepr.utils.scrape import ScrapeConfig

        result = await orch._scrape_company_website(
            company_url="https://example.com",
            company_name="Example",
            config=ScrapeConfig(),
        )
        assert result["success"] is False
        assert "unexpected error" in result["error"]
