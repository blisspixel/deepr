"""Shared fixtures for services tests."""

import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_openai_env(monkeypatch):
    """Set OPENAI_API_KEY in environment."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-not-real")


def make_chat_response(content):
    """Build a mock chat.completions.create return value.

    Args:
        content: String (raw text) or dict/list (auto-serialized to JSON)
    """
    if isinstance(content, (dict, list)):
        content = json.dumps(content)
    mock_msg = MagicMock()
    mock_msg.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


def make_responses_response(text):
    """Build a mock responses.create return value with output_text."""
    mock_resp = MagicMock()
    mock_resp.output_text = text
    return mock_resp
