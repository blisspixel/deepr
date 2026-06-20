"""Tests for deepr.backends.plan_quota.safety - auth-mode + no-surprise-bills."""

from __future__ import annotations

from deepr.backends.plan_quota.adapters import get_adapter
from deepr.backends.plan_quota.safety import AuthMode, detect_auth_mode, evaluate_plan_quota_safety


class TestDetectAuthMode:
    def test_clean_env_is_plan(self):
        assert detect_auth_mode(get_adapter("codex"), {}) == AuthMode.PLAN

    def test_metered_env_var_is_metered(self):
        assert detect_auth_mode(get_adapter("codex"), {"OPENAI_API_KEY": "sk-xxx"}) == AuthMode.METERED

    def test_blank_metered_var_is_still_plan(self):
        assert detect_auth_mode(get_adapter("codex"), {"OPENAI_API_KEY": "   "}) == AuthMode.PLAN

    def test_grok_api_key_is_metered(self):
        assert detect_auth_mode(get_adapter("grok"), {"XAI_API_KEY": "xai-x"}) == AuthMode.METERED


class TestSafetyGate:
    def test_plan_backend_clean_env_is_safe(self):
        d = evaluate_plan_quota_safety(get_adapter("codex"), env={})
        assert d.safe
        assert not d.requires_ack
        assert d.auth_mode == AuthMode.PLAN

    def test_api_key_present_blocks_with_guidance(self):
        d = evaluate_plan_quota_safety(get_adapter("codex"), env={"OPENAI_API_KEY": "sk-xxx"})
        assert not d.safe
        assert d.auth_mode == AuthMode.METERED
        assert "OPENAI_API_KEY" in d.reason
        assert "--api" in d.reason

    def test_metered_at_margin_backend_requires_ack(self):
        d = evaluate_plan_quota_safety(get_adapter("copilot"), env={})
        assert d.safe
        assert d.requires_ack
        assert "per call" in d.reason

    def test_tos_note_surfaced_for_gray_backend(self):
        d = evaluate_plan_quota_safety(get_adapter("kiro"), env={})
        assert d.safe
        assert "third-party-harness" in d.reason

    def test_decision_serializes(self):
        d = evaluate_plan_quota_safety(get_adapter("codex"), env={})
        payload = d.to_dict()
        assert payload["backend_id"] == "codex"
        assert payload["auth_mode"] == "plan"
        assert payload["safe"] is True
