from types import SimpleNamespace

import pytest

from deepr.experts import chat_capacity
from deepr.experts.chat_capacity import (
    METERED_EXPERT_CHAT_BLOCK_CODE,
    METERED_EXPERT_CHAT_CONFIRM_CODE,
    MeteredExpertChatDisabledError,
    expert_chat_capacity,
    require_expert_chat_dispatch,
)


def test_metered_dispatch_still_blocked_when_substrate_disabled(monkeypatch):
    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", False)
    monkeypatch.setenv("DEEPR_ALLOW_METERED_EXPERT_CHAT", "1")
    with pytest.raises(MeteredExpertChatDisabledError) as exc:
        require_expert_chat_dispatch(SimpleNamespace(metered=True), "expert_chat_turn")
    assert exc.value.code == METERED_EXPERT_CHAT_BLOCK_CODE


def test_metered_dispatch_requires_explicit_env_when_substrate_enabled(monkeypatch):
    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", True)
    monkeypatch.delenv("DEEPR_ALLOW_METERED_EXPERT_CHAT", raising=False)
    with pytest.raises(MeteredExpertChatDisabledError) as exc:
        require_expert_chat_dispatch(SimpleNamespace(metered=True), "expert_chat_turn")
    assert exc.value.code == METERED_EXPERT_CHAT_CONFIRM_CODE

    monkeypatch.setenv("DEEPR_ALLOW_METERED_EXPERT_CHAT", "1")
    require_expert_chat_dispatch(SimpleNamespace(metered=True), "expert_chat_turn")
    capacity = expert_chat_capacity(SimpleNamespace(metered=True))
    assert capacity["status"] == "available"
    assert capacity["explicit_allow"] is True


def test_owned_capacity_never_requires_metered_env(monkeypatch):
    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", False)
    monkeypatch.delenv("DEEPR_ALLOW_METERED_EXPERT_CHAT", raising=False)
    require_expert_chat_dispatch(SimpleNamespace(metered=False), "expert_chat_turn")
