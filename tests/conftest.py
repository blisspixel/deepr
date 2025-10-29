"""Pytest configuration and fixtures."""

import pytest
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load .env file for API keys in integration/E2E tests
load_dotenv()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir(tmp_path):
    """Provide temporary directory for tests."""
    return tmp_path


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for testing."""
    test_env = {
        "DEEPR_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test-key",
        "DEEPR_STORAGE": "local",
        "DEEPR_REPORTS_PATH": "./test_reports",
        "DEEPR_ENVIRONMENT": "local",
        "DEEPR_DEBUG": "true",
    }

    for key, value in test_env.items():
        monkeypatch.setenv(key, value)

    return test_env


@pytest.fixture
def mock_azure_env(monkeypatch):
    """Mock Azure environment variables."""
    test_env = {
        "DEEPR_PROVIDER": "azure",
        "AZURE_OPENAI_KEY": "test-azure-key",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
        "AZURE_DEPLOYMENT_O3": "test-o3-deployment",
        "AZURE_DEPLOYMENT_O4_MINI": "test-o4-mini-deployment",
        "DEEPR_STORAGE": "local",
        "DEEPR_ENVIRONMENT": "local",
    }

    for key, value in test_env.items():
        monkeypatch.setenv(key, value)

    return test_env


@pytest.fixture
def sample_research_job():
    """Provide sample research job for testing."""
    from deepr.queue import ResearchJob, JobStatus

    return ResearchJob(
        id="test-job-001",
        prompt="Test research prompt",
        model="o3-deep-research",
        status=JobStatus.QUEUED,
        priority=5,
    )
