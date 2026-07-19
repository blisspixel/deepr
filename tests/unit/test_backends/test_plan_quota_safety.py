"""Tests for deepr.backends.plan_quota.safety - auth-mode + no-surprise-bills."""

from __future__ import annotations

from deepr.backends.plan_quota.adapters import get_adapter
from deepr.backends.plan_quota.safety import (
    AuthMode,
    detect_auth_mode,
    evaluate_plan_quota_safety,
    plan_quota_child_env,
)


class TestDetectAuthMode:
    def test_clean_env_is_plan(self):
        assert detect_auth_mode(get_adapter("claude"), {}) == AuthMode.PLAN

    def test_metered_env_var_is_metered(self):
        assert detect_auth_mode(get_adapter("codex"), {"OPENAI_API_KEY": "sk-xxx"}) == AuthMode.METERED

    def test_blank_metered_var_is_still_plan(self):
        assert detect_auth_mode(get_adapter("codex"), {"OPENAI_API_KEY": "   "}) == AuthMode.PLAN

    def test_grok_api_key_is_metered(self):
        assert detect_auth_mode(get_adapter("grok"), {"XAI_API_KEY": "xai-x"}) == AuthMode.METERED

    def test_opencode_stored_auth_is_unknown(self):
        assert detect_auth_mode(get_adapter("opencode"), {}) == AuthMode.UNKNOWN

    def test_kiro_api_key_is_metered(self):
        assert detect_auth_mode(get_adapter("kiro"), {"kiro_api_key": "key-x"}) == AuthMode.METERED

    def test_case_collisions_cannot_hide_a_metered_key(self):
        env = {"anthropic_api_key": "key-x", "ANTHROPIC_API_KEY": ""}
        assert detect_auth_mode(get_adapter("claude"), env) == AuthMode.METERED


class TestSafetyGate:
    def test_plan_backend_clean_env_is_safe(self):
        d = evaluate_plan_quota_safety(get_adapter("claude"), env={})
        assert d.safe
        assert not d.requires_ack
        assert d.auth_mode == AuthMode.PLAN
        assert "live provider observation" in d.reason

    def test_api_key_present_is_truthfully_refused(self):
        d = evaluate_plan_quota_safety(get_adapter("codex"), env={"OPENAI_API_KEY": "sk-xxx"})
        assert not d.safe
        assert d.auth_mode == AuthMode.METERED
        assert "OPENAI_API_KEY" in d.reason
        assert "explicitly budgeted API path" in d.reason

    def test_child_env_is_a_runtime_allowlist(self):
        env = {
            "OPENAI_API_KEY": "sk-xxx",
            "AWS_SECRET_ACCESS_KEY": "aws-secret",
            "AZURE_STORAGE_CONNECTION_STRING": "azure-secret",
            "DEEPR_API_TOKEN": "deepr-secret",
            "PATH": "x",
            "HOME": "/home/operator",
            "CLAUDE_CONFIG_DIR": "/home/operator/.claude-test",
        }
        assert plan_quota_child_env(get_adapter("claude"), env) == {
            "PATH": "x",
            "HOME": "/home/operator",
            "CLAUDE_CONFIG_DIR": "/home/operator/.claude-test",
        }

    def test_metered_at_margin_backend_is_blocked_until_cost_accounting_exists(self):
        d = evaluate_plan_quota_safety(get_adapter("copilot"), env={})
        assert not d.safe
        assert not d.requires_ack
        assert "cost estimation" in d.reason
        assert "durable reservation" in d.reason
        assert "usage settlement" in d.reason
        assert "cost-ledger" in d.reason

    def test_native_read_backend_is_blocked(self):
        d = evaluate_plan_quota_safety(get_adapter("kiro"), env={})
        assert not d.safe
        assert "native read tools" in d.reason
        assert "explicit read allowlist" in d.reason

    def test_codex_native_tools_are_blocked(self):
        d = evaluate_plan_quota_safety(get_adapter("codex"), env={})
        assert not d.safe
        assert "native read and shell tools" in d.reason

    def test_opencode_unknown_stored_auth_is_blocked(self):
        d = evaluate_plan_quota_safety(get_adapter("opencode"), env={})
        assert not d.safe
        assert d.auth_mode == AuthMode.UNKNOWN
        assert "cannot be proven prepaid or local" in d.reason

    def test_decision_serializes(self):
        d = evaluate_plan_quota_safety(get_adapter("claude"), env={})
        payload = d.to_dict()
        assert payload["backend_id"] == "claude"
        assert payload["auth_mode"] == "plan"
        assert payload["safe"] is True
