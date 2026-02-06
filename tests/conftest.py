"""Pytest configuration and fixtures.

This module provides shared test infrastructure for the Deepr test suite:
- Mock providers, storage, and queue fixtures
- Environment variable mocking
- Sample data fixtures
- Hypothesis profile for CI stability

The fixtures are designed to enable comprehensive testing without
making actual API calls or incurring costs.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from dotenv import load_dotenv
from hypothesis import settings as hypothesis_settings, HealthCheck

# Load .env file for API keys in integration/E2E tests
load_dotenv()

# Suppress slow-generation health checks globally — property tests use complex
# strategies (nested dicts, filtered text) that can be slow on CI/Windows.
hypothesis_settings.register_profile(
    "ci",
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=None,
)
hypothesis_settings.load_profile("ci")


# =============================================================================
# PYTEST CONFIGURATION
# =============================================================================

def pytest_configure(config):
    """Register custom markers for test categorization."""
    config.addinivalue_line(
        "markers", "property: marks tests as property-based tests (Hypothesis)"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security-focused tests"
    )



# =============================================================================
# DIRECTORY FIXTURES
# =============================================================================

@pytest.fixture
def temp_dir(tmp_path):
    """Provide temporary directory for tests.
    
    Creates a fresh temporary directory for each test that needs
    isolated file system operations.
    """
    return tmp_path


# =============================================================================
# ENVIRONMENT FIXTURES
# =============================================================================

@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for OpenAI testing.
    
    Sets up a complete test environment with fake API keys
    to prevent accidental real API calls.
    """
    test_env = {
        "DEEPR_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test-key-not-real",
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
    """Mock Azure environment variables.
    
    Sets up Azure-specific configuration for testing
    Azure OpenAI provider integration.
    """
    test_env = {
        "DEEPR_PROVIDER": "azure",
        "AZURE_OPENAI_KEY": "test-azure-key-not-real",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
        "AZURE_DEPLOYMENT_O3": "test-o3-deployment",
        "AZURE_DEPLOYMENT_O4_MINI": "test-o4-mini-deployment",
        "DEEPR_STORAGE": "local",
        "DEEPR_ENVIRONMENT": "local",
    }

    for key, value in test_env.items():
        monkeypatch.setenv(key, value)

    return test_env


# =============================================================================
# MOCK PROVIDER FIXTURES
# =============================================================================

@pytest.fixture
def mock_provider():
    """Create a mock DeepResearchProvider.
    
    Provides a fully mocked provider that simulates API responses
    without making real network calls. All async methods return
    sensible defaults.
    
    Returns:
        AsyncMock configured as a DeepResearchProvider
    """
    provider = AsyncMock()
    
    # Configure submit_research to return a job ID
    provider.submit_research = AsyncMock(return_value="job-test-12345")
    
    # Configure get_status to return a completed response
    mock_response = MagicMock()
    mock_response.status = "completed"
    mock_response.text = "Test research results"
    mock_response.metadata = {"report_title": "Test Report"}
    provider.get_status = AsyncMock(return_value=mock_response)
    
    # Configure cancel_job
    provider.cancel_job = AsyncMock(return_value=True)
    
    # Configure vector store operations
    provider.delete_vector_store = AsyncMock(return_value=True)
    
    # Configure file operations
    mock_file = MagicMock()
    mock_file.id = "file-test-12345"
    provider.upload_file = AsyncMock(return_value=mock_file)
    
    return provider


@pytest.fixture
def mock_storage():
    """Create a mock StorageBackend.
    
    Provides a fully mocked storage backend for testing
    without actual file system or cloud storage operations.
    
    Returns:
        AsyncMock configured as a StorageBackend
    """
    storage = AsyncMock()
    
    # Configure save_report
    storage.save_report = AsyncMock(return_value=True)
    
    # Configure get_content_type
    storage.get_content_type = MagicMock(return_value="text/markdown")
    
    # Configure load operations
    storage.load_report = AsyncMock(return_value="# Test Report\n\nContent here.")
    
    return storage


@pytest.fixture
def mock_document_manager():
    """Create a mock DocumentManager.
    
    Provides a fully mocked document manager for testing
    document upload and vector store creation.
    
    Returns:
        MagicMock configured as a DocumentManager
    """
    doc_manager = MagicMock()
    
    # Configure upload_documents to return file IDs
    doc_manager.upload_documents = AsyncMock(
        return_value=["file-1", "file-2"]
    )
    
    # Configure create_vector_store
    mock_vector_store = MagicMock()
    mock_vector_store.id = "vs-test-12345"
    doc_manager.create_vector_store = AsyncMock(return_value=mock_vector_store)
    
    return doc_manager


@pytest.fixture
def mock_report_generator():
    """Create a mock ReportGenerator.
    
    Provides a fully mocked report generator for testing
    report generation without actual document processing.
    
    Returns:
        MagicMock configured as a ReportGenerator
    """
    generator = MagicMock()
    
    # Configure extract_text_from_response
    generator.extract_text_from_response = MagicMock(
        return_value="# Research Results\n\nFindings here."
    )
    
    # Configure generate_reports
    generator.generate_reports = AsyncMock(return_value={
        "md": "# Report\n\nContent",
        "html": "<h1>Report</h1><p>Content</p>",
    })
    
    return generator


@pytest.fixture
def mock_cost_safety_manager():
    """Create a mock CostSafetyManager.
    
    Provides a mocked cost safety manager that approves all
    operations by default. Can be configured per-test for
    budget limit testing.
    
    Returns:
        MagicMock configured as a CostSafetyManager
    """
    manager = MagicMock()
    
    # Default: allow all operations
    manager.check_operation = MagicMock(
        return_value=(True, "Approved", False)
    )
    
    # Configure record_cost
    manager.record_cost = MagicMock()
    
    # Configure get_session_cost
    manager.get_session_cost = MagicMock(return_value=0.0)
    
    return manager


# =============================================================================
# RESEARCH ORCHESTRATOR FIXTURE
# =============================================================================

@pytest.fixture
def mock_orchestrator(mock_provider, mock_storage, mock_document_manager, mock_report_generator):
    """Create a ResearchOrchestrator with all dependencies mocked.
    
    This fixture assembles a complete orchestrator instance with
    mocked dependencies, ready for unit testing orchestration logic.
    
    Args:
        mock_provider: Mocked provider fixture
        mock_storage: Mocked storage fixture
        mock_document_manager: Mocked document manager fixture
        mock_report_generator: Mocked report generator fixture
        
    Returns:
        ResearchOrchestrator with mocked dependencies
    """
    from deepr.core.research import ResearchOrchestrator
    
    return ResearchOrchestrator(
        provider=mock_provider,
        storage=mock_storage,
        document_manager=mock_document_manager,
        report_generator=mock_report_generator,
        system_message="Test system message for unit tests."
    )


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_research_job():
    """Provide sample research job for testing.
    
    Creates a ResearchJob instance with typical values
    for testing queue and job management functionality.
    """
    from deepr.queue import ResearchJob, JobStatus

    return ResearchJob(
        id="test-job-001",
        prompt="Test research prompt",
        model="o3-deep-research",
        status=JobStatus.QUEUED,
        priority=5,
    )


@pytest.fixture
def sample_expert_profile():
    """Provide sample expert profile for testing.
    
    Creates an ExpertProfile instance with typical values
    for testing expert management functionality.
    """
    from deepr.experts.profile import ExpertProfile
    
    return ExpertProfile(
        name="Test Expert",
        vector_store_id="vs-test-12345",
        description="A test expert for unit testing",
        domain="Software Testing",
        domain_velocity="medium",
        total_documents=5,
        conversations=10,
        research_triggered=3,
        total_research_cost=2.50,
    )


@pytest.fixture
def sample_research_request():
    """Provide sample research request data.
    
    Returns a dictionary with typical research request
    parameters for testing submission logic.
    """
    return {
        "prompt": "What are the best practices for Python testing?",
        "model": "o3-deep-research",
        "enable_web_search": True,
        "enable_code_interpreter": False,
        "budget_limit": 1.00,
    }


# =============================================================================
# CLI TESTING FIXTURES
# =============================================================================

@pytest.fixture
def cli_runner():
    """Provide Click CLI test runner.
    
    Creates a CliRunner instance for testing CLI commands
    in isolation without actual terminal interaction.
    """
    from click.testing import CliRunner
    return CliRunner()


@pytest.fixture
def mock_cli_context(mock_env, mock_provider, mock_storage):
    """Create a mock CLI context with all dependencies.
    
    Sets up the environment and mocks needed for CLI
    command testing.
    """
    return {
        "env": mock_env,
        "provider": mock_provider,
        "storage": mock_storage,
    }


# =============================================================================
# API TESTING FIXTURES
# =============================================================================

@pytest.fixture
def api_client():
    """Provide Flask test client for API testing.
    
    Creates a test client for the Flask API application
    with testing mode enabled.
    
    Note: The API module uses module-level globals (queue, provider, storage)
    that are initialized at import time. Tests should use patch.object()
    to mock these globals as needed.
    """
    from deepr.api.app import app
    
    app.config["TESTING"] = True
    
    with app.test_client() as client:
        yield client


@pytest.fixture
def api_headers():
    """Provide standard API request headers.
    
    Returns headers commonly used in API requests
    for consistent testing.
    """
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
