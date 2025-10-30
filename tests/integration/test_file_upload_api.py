"""Integration tests for file upload functionality with real API calls.

These tests validate that the actual file upload workflow works end-to-end:
1. File upload to provider
2. Vector store creation
3. Research submission with file_search tool
4. Correct tool parameter formatting

This test suite specifically addresses the bug discovered on Oct 30, 2025 where
file uploads failed 4 times due to incorrect tool parameter formatting.

IMPORTANT: These tests make REAL API calls and COST MONEY.
Run explicitly with: pytest -m "requires_api and file_upload"
"""

import pytest
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from deepr.providers.openai_provider import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig


@pytest.fixture
def test_file(tmp_path):
    """Create a temporary test file for upload."""
    test_file = tmp_path / "test_document.txt"
    test_file.write_text("""
# Test Document

This is a test document for validating file upload functionality.

## Key Points
- Point 1: File upload should work
- Point 2: Vector stores should be created
- Point 3: Research should use the uploaded files

## Test Data
The answer to the test question is: 42
""")
    return test_file


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.file_upload
async def test_openai_file_upload_basic(test_file):
    """Test basic file upload with OpenAI provider.

    This test validates:
    - File can be uploaded to OpenAI
    - Vector store is created successfully
    - Files are associated with vector store
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    provider = OpenAIProvider()

    # Upload file
    file_id = await provider.upload_document(str(test_file))
    assert file_id is not None
    assert file_id.startswith("file_")

    # Create vector store
    vector_store_id = await provider.create_vector_store(
        file_ids=[file_id],
        name="test_vector_store"
    )
    assert vector_store_id is not None
    assert vector_store_id.startswith("vs_")

    print(f"File uploaded: {file_id}")
    print(f"Vector store created: {vector_store_id}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.file_upload
async def test_openai_research_with_file_upload(test_file):
    """Test full research workflow with file upload.

    This is the EXACT scenario that failed 4 times on Oct 30, 2025.

    Expected tool configuration:
    - file_search: Has vector_store_ids, NO container
    - web_search_preview: NO container
    - code_interpreter: HAS container = {"type": "auto"}
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    provider = OpenAIProvider()

    # Upload file
    file_id = await provider.upload_document(str(test_file))
    vector_store_id = await provider.create_vector_store(
        file_ids=[file_id],
        name="test_research_vector_store"
    )

    # Create research request with file_search tool
    # This is the configuration that previously failed
    request = ResearchRequest(
        prompt="Based on the uploaded document, what is the answer to the test question?",
        model="o4-mini-deep-research",
        system_message="You are a helpful assistant. Use the uploaded document to answer.",
        tools=[
            ToolConfig(type="file_search", vector_store_ids=[vector_store_id]),
            ToolConfig(type="web_search_preview"),
            ToolConfig(type="code_interpreter"),
        ],
        background=True
    )

    # This should NOT raise BadRequestError about unknown/missing container parameters
    job_id = await provider.submit_research(request)
    assert job_id is not None
    assert job_id.startswith("resp_")

    print(f"Research submitted successfully: {job_id}")

    # Poll for completion (with reasonable timeout)
    max_wait = 120  # 2 minutes
    poll_interval = 5
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)

        if response.status == "completed":
            # Validate response structure
            assert response.output is not None
            assert len(response.output) > 0

            # Check that response contains content
            has_content = False
            for block in response.output:
                if block.get('type') == 'message':
                    for item in block.get('content', []):
                        if item.get('type') in ['output_text', 'text']:
                            text = item.get('text', '')
                            if text and len(text) > 0:
                                has_content = True
                                print(f"Response preview: {text[:200]}...")
                                break

            assert has_content, "Response should contain text content"

            # Validate cost
            assert response.usage is not None
            assert response.usage.cost < 1.0, "Simple file search query should be cheap"

            print(f"Research completed. Cost: ${response.usage.cost:.4f}")
            return

        elif response.status == "failed":
            pytest.fail(f"Research job failed: {response.error}")

    pytest.fail(f"Research job timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.file_upload
async def test_openai_tool_parameter_validation():
    """Test that tool parameters are correctly formatted for OpenAI API.

    This test makes an actual API call to validate that our tool formatting
    is correct. If tool parameters are wrong, OpenAI will return a 400 error.

    This is a regression test for the Oct 30, 2025 container parameter bug.
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    provider = OpenAIProvider()

    # Test with web_search_preview (should NOT have container)
    request_web_search = ResearchRequest(
        prompt="What is 2+2?",
        model="o4-mini-deep-research",
        system_message="You are a calculator.",
        tools=[ToolConfig(type="web_search_preview")],
        background=True
    )

    # This should NOT raise: Unknown parameter: 'tools[0].container'
    job_id_1 = await provider.submit_research(request_web_search)
    assert job_id_1 is not None
    print(f"web_search_preview test passed: {job_id_1}")

    # Test with code_interpreter (MUST have container)
    request_code = ResearchRequest(
        prompt="Calculate 2+2 using code.",
        model="o4-mini-deep-research",
        system_message="You are a calculator. Use code to calculate.",
        tools=[ToolConfig(type="code_interpreter")],
        background=True
    )

    # This should NOT raise: Missing required parameter: 'tools[0].container'
    job_id_2 = await provider.submit_research(request_code)
    assert job_id_2 is not None
    print(f"code_interpreter test passed: {job_id_2}")

    # Test with multiple tools (the real-world scenario)
    request_multiple = ResearchRequest(
        prompt="Research Python and write a simple script.",
        model="o4-mini-deep-research",
        system_message="You are a helpful assistant.",
        tools=[
            ToolConfig(type="web_search_preview"),  # NO container
            ToolConfig(type="code_interpreter"),     # HAS container
        ],
        background=True
    )

    # This should NOT raise any parameter errors
    job_id_3 = await provider.submit_research(request_multiple)
    assert job_id_3 is not None
    print(f"Multiple tools test passed: {job_id_3}")

    print("\nAll tool parameter validation tests passed!")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.file_upload
async def test_file_upload_with_readme_and_roadmap(tmp_path):
    """Test file upload with README and ROADMAP (mimics actual failed scenario).

    This recreates the exact scenario from Oct 30, 2025 that failed 4 times.
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    # Create mock README and ROADMAP files
    readme = tmp_path / "README.md"
    readme.write_text("""
# Test Project

This is a test project for validating file upload with multiple files.

## Features
- Feature 1
- Feature 2
""")

    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text("""
# Roadmap

## Version 1.0
- Implement feature 1
- Implement feature 2

## Version 2.0
- Advanced features
""")

    provider = OpenAIProvider()

    # Upload both files
    file_id_1 = await provider.upload_document(str(readme))
    file_id_2 = await provider.upload_document(str(roadmap))

    # Create vector store with both files
    vector_store_id = await provider.create_vector_store(
        file_ids=[file_id_1, file_id_2],
        name="test_multi_file_vector_store"
    )

    # Create research request (exact configuration that failed)
    request = ResearchRequest(
        prompt="Based on the README and ROADMAP, summarize the project in one sentence.",
        model="o4-mini-deep-research",
        system_message="You are a helpful assistant. Use the uploaded documents.",
        tools=[
            ToolConfig(type="file_search", vector_store_ids=[vector_store_id]),
            ToolConfig(type="web_search_preview"),
            ToolConfig(type="code_interpreter"),
        ],
        background=True
    )

    # This is where the 4 failures occurred - should now succeed
    job_id = await provider.submit_research(request)
    assert job_id is not None

    print(f"Multi-file research submitted successfully: {job_id}")

    # We don't need to wait for completion in this test
    # The fact that it submitted without errors is the validation


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tool_parameter_format_without_api():
    """Test tool parameter formatting WITHOUT making API call (free test).

    This validates that our internal formatting is correct without incurring costs.
    Uses mocked API client to inspect parameters.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    provider = OpenAIProvider(api_key="test-key")

    mock_response = MagicMock()
    mock_response.id = "resp_test123"

    with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        request = ResearchRequest(
            prompt="Test",
            model="o4-mini-deep-research",
            system_message="Test",
            tools=[
                ToolConfig(type="file_search", vector_store_ids=["vs_123"]),
                ToolConfig(type="web_search_preview"),
                ToolConfig(type="code_interpreter"),
            ],
        )

        await provider.submit_research(request)

        # Validate the parameters passed to the API
        call_kwargs = mock_create.call_args.kwargs
        tools = call_kwargs["tools"]

        # file_search: has vector_store_ids, NO container
        assert tools[0]["type"] == "file_search"
        assert "vector_store_ids" in tools[0]
        assert "container" not in tools[0], "file_search should NOT have container"

        # web_search_preview: NO container
        assert tools[1]["type"] == "web_search_preview"
        assert "container" not in tools[1], "web_search_preview should NOT have container"

        # code_interpreter: HAS container
        assert tools[2]["type"] == "code_interpreter"
        assert "container" in tools[2], "code_interpreter MUST have container"
        assert tools[2]["container"] == {"type": "auto"}

        print("Tool parameter format validation passed (no API call)")
