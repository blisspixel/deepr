"""Tests for deepr.backends.plan_quota.safety - auth-mode + no-surprise-bills."""

from __future__ import annotations

from deepr.backends.plan_quota.adapters import get_adapter
from deepr.backends.plan_quota.safety import (
    AuthMode,
    detect_auth_mode,
    evaluate_plan_quota_safety,
    plan_quota_child_env,
)


def _unfiltered_child_env(monkeypatch):
    """Simulate a metered var reaching the child, to prove the gate still bites."""
    from deepr.backends.plan_quota import safety

    monkeypatch.setattr(safety, "plan_quota_child_env", lambda adapter, env: dict(env))


class TestDetectAuthMode:
    """Auth mode is decided by what the dispatch can reach, not what exists.

    Policy: free capacity (plan/local) is the default and must not be blocked by
    a credential the operator holds for other tools. Metered spend is a last
    resort, explicitly requested and costed. So the money guard belongs on
    *reachability*, not on *presence*.
    """

    def test_clean_env_is_plan(self):
        assert detect_auth_mode(get_adapter("claude"), {}) == AuthMode.PLAN

    def test_held_key_that_cannot_reach_the_child_does_not_block_free_capacity(self):
        env = {"ANTHROPIC_API_KEY": "sk-ant-xxx", "PATH": "/usr/bin"}
        assert "ANTHROPIC_API_KEY" not in plan_quota_child_env(get_adapter("claude"), env)
        assert detect_auth_mode(get_adapter("claude"), env) == AuthMode.PLAN

    def test_reachable_metered_var_is_still_metered(self, monkeypatch):
        """The gate must remain able to refuse; this proves it was not disabled."""
        _unfiltered_child_env(monkeypatch)
        assert detect_auth_mode(get_adapter("codex"), {"OPENAI_API_KEY": "sk-xxx"}) == AuthMode.METERED

    def test_reachable_grok_key_is_metered(self, monkeypatch):
        _unfiltered_child_env(monkeypatch)
        assert detect_auth_mode(get_adapter("grok"), {"XAI_API_KEY": "xai-x"}) == AuthMode.METERED

    def test_reachable_kiro_key_is_metered(self, monkeypatch):
        _unfiltered_child_env(monkeypatch)
        assert detect_auth_mode(get_adapter("kiro"), {"kiro_api_key": "key-x"}) == AuthMode.METERED

    def test_case_collisions_cannot_hide_a_reachable_key(self, monkeypatch):
        _unfiltered_child_env(monkeypatch)
        env = {"anthropic_api_key": "key-x", "ANTHROPIC_API_KEY": ""}
        assert detect_auth_mode(get_adapter("claude"), env) == AuthMode.METERED

    def test_metered_vars_stripped_even_if_added_to_the_allowlist(self, monkeypatch):
        """Removal by name, so the guarantee does not depend on the allowlist."""
        from deepr.backends.plan_quota import safety

        monkeypatch.setattr(safety, "_PLAN_CHILD_ENV_ALLOWLIST", frozenset({"PATH", "ANTHROPIC_API_KEY"}))
        child = safety.plan_quota_child_env(get_adapter("claude"), {"ANTHROPIC_API_KEY": "k", "PATH": "/usr/bin"})
        assert "ANTHROPIC_API_KEY" not in child
        assert child["PATH"] == "/usr/bin"

    def test_blank_metered_var_is_still_plan(self):
        assert detect_auth_mode(get_adapter("codex"), {"OPENAI_API_KEY": "   "}) == AuthMode.PLAN

    def test_opencode_stored_auth_is_unknown(self):
        assert detect_auth_mode(get_adapter("opencode"), {}) == AuthMode.UNKNOWN

    def test_unverified_stored_auth_stays_unknown_even_with_a_clean_child(self):
        """Closing the env path does not prove which stored credential is used."""
        assert detect_auth_mode(get_adapter("opencode"), {"OPENAI_API_KEY": "sk-x"}) == AuthMode.UNKNOWN

    def test_other_adapters_remain_blocked_by_their_own_gates(self):
        """Every other adapter is either blocked or confined at dispatch.

        grok, antigravity and codex are confined rather than blocked, which is
        strictly better: the invariant holds and the backend stays usable.
        test_plan_quota_adapters pins the confinement itself.
        """
        confined = {"grok", "antigravity", "codex"}
        for backend_id in ("codex", "grok", "kiro", "opencode", "antigravity"):
            adapter = get_adapter(backend_id)
            assert adapter is not None
            if backend_id in confined:
                argv = " ".join(adapter.argv_builder("p.txt", None))
                assert "--disallowed-tools" in argv or "--sandbox" in argv, backend_id
                continue
            assert adapter.execution_block_reason, f"{backend_id} lost its execution block"


class TestSafetyGate:
    def test_plan_backend_clean_env_is_safe(self):
        d = evaluate_plan_quota_safety(get_adapter("claude"), env={})
        assert d.safe
        assert not d.requires_ack
        assert d.auth_mode == AuthMode.PLAN
        assert "live provider observation" in d.reason

    def test_reachable_api_key_is_truthfully_refused(self, monkeypatch):
        """A key the child can read still refuses, and names the variable."""
        _unfiltered_child_env(monkeypatch)
        d = evaluate_plan_quota_safety(get_adapter("codex"), env={"OPENAI_API_KEY": "sk-xxx"})
        assert not d.safe
        assert d.auth_mode == AuthMode.METERED
        assert "OPENAI_API_KEY" in d.reason
        assert "explicitly budgeted API path" in d.reason

    def test_held_key_does_not_block_prepaid_capacity(self):
        """The policy in one test: having a key is not spending it."""
        d = evaluate_plan_quota_safety(get_adapter("claude"), env={"ANTHROPIC_API_KEY": "sk-ant-xxx"})
        assert d.auth_mode == AuthMode.PLAN
        assert d.safe

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

    def test_codex_is_safe_once_its_sandbox_confines_the_tools(self):
        """Codex was gated on native tools; it now runs read-only and offline.

        The gate existed to stop an untrusted prompt reaching live file and
        shell tools. An OS sandbox satisfies that as well as a tool allowlist
        does, so the refusal was pinning the mechanism rather than the property.
        """
        d = evaluate_plan_quota_safety(get_adapter("codex"), env={})
        assert d.safe, d.reason

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
