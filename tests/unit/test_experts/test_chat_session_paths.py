"""Path safety for expert chat conversation session ids."""

from __future__ import annotations

from types import SimpleNamespace

from deepr.experts.chat import ExpertChatSession
from deepr.experts.command_handlers import handle_load
from deepr.experts.commands import CommandResult


def test_save_conversation_rejects_windows_device_session_id(tmp_path, monkeypatch) -> None:
    conversations = tmp_path / "conversations"
    conversations.mkdir()
    monkeypatch.setattr(
        "deepr.experts.chat.ExpertStore",
        lambda: SimpleNamespace(get_conversations_dir=lambda _name: conversations),
    )
    session = ExpertChatSession.__new__(ExpertChatSession)
    session.expert = SimpleNamespace(name="TKG")
    session.messages = []
    session.research_jobs = []
    session.agentic = False
    session.reasoning_trace = []
    session.get_session_summary = lambda: {}
    session.thought_stream = SimpleNamespace(get_trace=lambda: [], log_path=tmp_path / "thoughts.jsonl")

    saved = session.save_conversation("CON")

    assert saved != "CON"
    assert not (conversations / "CON.json").exists()
    assert (conversations / f"{saved}.json").exists()


async def test_load_conversation_rejects_windows_device_session_id() -> None:
    session = SimpleNamespace(expert=SimpleNamespace(name="TKG"), messages=[])
    result = await handle_load(session, "NUL", {})
    assert isinstance(result, CommandResult)
    assert result.success is False
    assert "Invalid session id" in result.output
