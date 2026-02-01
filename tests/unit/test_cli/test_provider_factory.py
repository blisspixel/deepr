"""Tests for CLI provider factory module.

Tests centralized provider initialization and API key retrieval.
Requirements: 6.2 - Centralize provider initialization logic
"""

import pytest
from unittest.mock import patch, MagicMock


class TestGetApiKey:
    """Tests for get_api_key function."""
    
    def test_get_openai_api_key(self):
        """Test getting OpenAI API key."""
        from deepr.cli.commands.provider_factory import get_api_key
        
        config = {"api_key": "sk-test-key"}
        key = get_api_key("openai", config)
        
        assert key == "sk-test-key"
    
    def test_get_gemini_api_key(self):
        """Test getting Gemini API key."""
        from deepr.cli.commands.provider_factory import get_api_key
        
        config = {"gemini_api_key": "gemini-test-key"}
        key = get_api_key("gemini", config)
        
        assert key == "gemini-test-key"
    
    def test_get_grok_api_key(self):
        """Test getting Grok/xAI API key."""
        from deepr.cli.commands.provider_factory import get_api_key
        
        config = {"xai_api_key": "xai-test-key"}
        key = get_api_key("grok", config)
        
        assert key == "xai-test-key"
    
    def test_get_xai_api_key(self):
        """Test getting xAI API key directly."""
        from deepr.cli.commands.provider_factory import get_api_key
        
        config = {"xai_api_key": "xai-test-key"}
        key = get_api_key("xai", config)
        
        assert key == "xai-test-key"
    
    def test_get_azure_api_key(self):
        """Test getting Azure API key."""
        from deepr.cli.commands.provider_factory import get_api_key
        
        config = {"azure_api_key": "azure-test-key"}
        key = get_api_key("azure", config)
        
        assert key == "azure-test-key"
    
    def test_missing_api_key_raises_error(self):
        """Test that missing API key raises ValueError."""
        from deepr.cli.commands.provider_factory import get_api_key
        
        config = {}
        
        with pytest.raises(ValueError, match="No API key found"):
            get_api_key("openai", config)
    
    def test_loads_config_if_not_provided(self):
        """Test that config is loaded from env if not provided."""
        from deepr.cli.commands.provider_factory import get_api_key
        
        with patch("deepr.cli.commands.provider_factory.load_config") as mock_load:
            mock_load.return_value = {"api_key": "loaded-key"}
            
            key = get_api_key("openai")
            
            mock_load.assert_called_once()
            assert key == "loaded-key"


class TestGetToolName:
    """Tests for get_tool_name function."""
    
    def test_openai_web_search_tool(self):
        """Test OpenAI web search tool name."""
        from deepr.cli.commands.provider_factory import get_tool_name
        
        name = get_tool_name("openai", "web_search")
        
        assert name == "web_search_preview"
    
    def test_grok_web_search_tool(self):
        """Test Grok web search tool name."""
        from deepr.cli.commands.provider_factory import get_tool_name
        
        name = get_tool_name("grok", "web_search")
        
        assert name == "web_search"
    
    def test_xai_web_search_tool(self):
        """Test xAI web search tool name."""
        from deepr.cli.commands.provider_factory import get_tool_name
        
        name = get_tool_name("xai", "web_search")
        
        assert name == "web_search"
    
    def test_code_interpreter_same_for_all(self):
        """Test code interpreter name is same for all providers."""
        from deepr.cli.commands.provider_factory import get_tool_name
        
        assert get_tool_name("openai", "code_interpreter") == "code_interpreter"
        assert get_tool_name("grok", "code_interpreter") == "code_interpreter"
    
    def test_unknown_tool_returns_as_is(self):
        """Test unknown tool type returns as-is."""
        from deepr.cli.commands.provider_factory import get_tool_name
        
        name = get_tool_name("openai", "custom_tool")
        
        assert name == "custom_tool"


class TestSupportsBackgroundJobs:
    """Tests for supports_background_jobs function."""
    
    def test_openai_supports_background(self):
        """Test OpenAI supports background jobs."""
        from deepr.cli.commands.provider_factory import supports_background_jobs
        
        assert supports_background_jobs("openai") is True
    
    def test_azure_supports_background(self):
        """Test Azure supports background jobs."""
        from deepr.cli.commands.provider_factory import supports_background_jobs
        
        assert supports_background_jobs("azure") is True
    
    def test_gemini_no_background(self):
        """Test Gemini doesn't support background jobs."""
        from deepr.cli.commands.provider_factory import supports_background_jobs
        
        assert supports_background_jobs("gemini") is False
    
    def test_grok_no_background(self):
        """Test Grok doesn't support background jobs."""
        from deepr.cli.commands.provider_factory import supports_background_jobs
        
        assert supports_background_jobs("grok") is False


class TestSupportsVectorStores:
    """Tests for supports_vector_stores function."""
    
    def test_openai_supports_vector_stores(self):
        """Test OpenAI supports vector stores."""
        from deepr.cli.commands.provider_factory import supports_vector_stores
        
        assert supports_vector_stores("openai") is True
    
    def test_azure_supports_vector_stores(self):
        """Test Azure supports vector stores."""
        from deepr.cli.commands.provider_factory import supports_vector_stores
        
        assert supports_vector_stores("azure") is True
    
    def test_gemini_no_vector_stores(self):
        """Test Gemini doesn't support vector stores."""
        from deepr.cli.commands.provider_factory import supports_vector_stores
        
        assert supports_vector_stores("gemini") is False


class TestNormalizeProviderName:
    """Tests for normalize_provider_name function."""
    
    def test_grok_normalizes_to_xai(self):
        """Test grok normalizes to xai."""
        from deepr.cli.commands.provider_factory import normalize_provider_name
        
        assert normalize_provider_name("grok") == "xai"
    
    def test_openai_unchanged(self):
        """Test openai stays unchanged."""
        from deepr.cli.commands.provider_factory import normalize_provider_name
        
        assert normalize_provider_name("openai") == "openai"
    
    def test_case_insensitive(self):
        """Test normalization is case insensitive."""
        from deepr.cli.commands.provider_factory import normalize_provider_name
        
        assert normalize_provider_name("GROK") == "xai"
        assert normalize_provider_name("OpenAI") == "openai"


class TestCreateProviderInstance:
    """Tests for create_provider_instance function."""
    
    def test_creates_provider_with_api_key(self):
        """Test provider is created with correct API key."""
        from deepr.cli.commands.provider_factory import create_provider_instance
        
        config = {"api_key": "test-key"}
        
        # Patch at source module since import happens inside function
        with patch("deepr.providers.create_provider") as mock_create:
            mock_provider = MagicMock()
            mock_create.return_value = mock_provider
            
            result = create_provider_instance("openai", config)
            
            mock_create.assert_called_once_with("openai", api_key="test-key")
            assert result == mock_provider
