from types import SimpleNamespace

import pytest

from deepr.experts import chat_capacity
from deepr.experts.chat_capacity import (
    METERED_EXPERT_CHAT_BLOCK_CODE,
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


def test_metered_dispatch_cannot_be_enabled_by_flag_or_environment(monkeypatch):
    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", True)
    monkeypatch.setenv("DEEPR_ALLOW_METERED_EXPERT_CHAT", "1")
    with pytest.raises(MeteredExpertChatDisabledError) as exc:
        require_expert_chat_dispatch(SimpleNamespace(metered=True), "expert_chat_turn")
    assert exc.value.code == METERED_EXPERT_CHAT_BLOCK_CODE

    capacity = expert_chat_capacity(SimpleNamespace(metered=True))
    assert capacity["status"] == "blocked"
    assert capacity["execution_enabled"] is False
    assert capacity["explicit_allow"] is False


def test_owned_capacity_never_requires_metered_env(monkeypatch):
    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", False)
    monkeypatch.delenv("DEEPR_ALLOW_METERED_EXPERT_CHAT", raising=False)
    require_expert_chat_dispatch(SimpleNamespace(metered=False), "expert_chat_turn")


def test_release_invariant_blocks_metered_chat_without_full_charge_envelope(monkeypatch):
    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", True)
    monkeypatch.setattr(chat_capacity, "HOSTED_EXPERT_STORAGE_LIFECYCLE_ACCOUNTING_ENABLED", False)

    with pytest.raises(RuntimeError, match="provider-enforceable maximum-charge envelopes"):
        chat_capacity.validate_expert_chat_release_invariants()
