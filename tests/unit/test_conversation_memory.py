"""Unit tests for conversation memory persistence."""
import pytest
import asyncio
import json
from pathlib import Path
from deepr.experts.chat import start_chat_session
from deepr.experts.profile import ExpertStore

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_save_conversation():
    """Test that conversations are saved to disk."""
    # Start session
    session = await start_chat_session(
        "Agentic Digital Consciousness",
        budget=1.0,
        agentic=False
    )

    # Send a message
    await session.send_message("What is agentic AI?")

    # Save conversation
    session_id = session.save_conversation()

    assert session_id is not None
    assert len(session_id) > 0

    # Verify file exists
    store = ExpertStore()
    conversations_dir = store.get_conversations_dir("Agentic Digital Consciousness")
    conversation_file = conversations_dir / f"{session_id}.json"

    assert conversation_file.exists()

    # Load and verify content
    with open(conversation_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert data["session_id"] == session_id
    assert data["expert_name"] == "Agentic Digital Consciousness"
    assert len(data["messages"]) >= 2  # At least user + assistant
    assert data["summary"]["messages_exchanged"] == 1
    assert "cost_accumulated" in data["summary"]

    # Cleanup
    conversation_file.unlink()


@pytest.mark.asyncio
async def test_conversation_structure():
    """Test conversation data structure."""
    session = await start_chat_session(
        "Agentic Digital Consciousness",
        budget=0.5,
        agentic=True
    )

    await session.send_message("Test question")
    session_id = session.save_conversation()

    # Load conversation
    store = ExpertStore()
    conversations_dir = store.get_conversations_dir("Agentic Digital Consciousness")
    conversation_file = conversations_dir / f"{session_id}.json"

    with open(conversation_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Check structure
    assert "session_id" in data
    assert "expert_name" in data
    assert "started_at" in data
    assert "ended_at" in data
    assert "messages" in data
    assert "summary" in data
    assert "research_jobs" in data
    assert "agentic_mode" in data

    # Check agentic mode was saved
    assert data["agentic_mode"] is True

    # Cleanup
    conversation_file.unlink()


@pytest.mark.asyncio
async def test_multiple_conversations():
    """Test saving multiple conversations."""
    session1 = await start_chat_session(
        "Agentic Digital Consciousness",
        budget=1.0
    )

    await session1.send_message("First question")
    session_id1 = session1.save_conversation()

    session2 = await start_chat_session(
        "Agentic Digital Consciousness",
        budget=1.0
    )

    await session2.send_message("Second question")
    session_id2 = session2.save_conversation()

    # Verify both files exist
    store = ExpertStore()
    conversations_dir = store.get_conversations_dir("Agentic Digital Consciousness")

    file1 = conversations_dir / f"{session_id1}.json"
    file2 = conversations_dir / f"{session_id2}.json"

    assert file1.exists()
    assert file2.exists()
    assert session_id1 != session_id2

    # Cleanup
    file1.unlink()
    file2.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
