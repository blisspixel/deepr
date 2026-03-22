"""Tests for permission boundaries and policy enforcement."""

from deepr.security.permissions import (
    PermissionEnforcer,
    PermissionPolicy,
)


class TestPermissionPolicy:
    def test_defaults(self):
        p = PermissionPolicy()
        assert p.allow_write is True
        assert p.allow_code_execution is False
        assert p.budget_per_session == 0.0

    def test_restrictive_preset(self):
        p = PermissionPolicy.restrictive()
        assert p.allow_write is False
        assert p.allow_external_requests is False
        assert p.budget_per_session == 1.0
        assert "search_knowledge_base" in p.tool_allowlist

    def test_open_preset(self):
        p = PermissionPolicy.open()
        assert p.allow_write is True
        assert p.tool_allowlist == []

    def test_roundtrip(self):
        original = PermissionPolicy(
            name="test",
            tool_allowlist=["search_knowledge_base"],
            budget_per_session=5.0,
            allow_write=False,
        )
        restored = PermissionPolicy.from_dict(original.to_dict())
        assert restored.name == "test"
        assert restored.tool_allowlist == ["search_knowledge_base"]
        assert restored.budget_per_session == 5.0
        assert restored.allow_write is False


class TestPermissionEnforcerTools:
    def test_open_policy_allows_all(self):
        enforcer = PermissionEnforcer(PermissionPolicy.open())
        assert enforcer.check_tool("deep_research").allowed
        assert enforcer.check_tool("anything").allowed

    def test_allowlist_blocks_unlisted(self):
        policy = PermissionPolicy(tool_allowlist=["search_knowledge_base"])
        enforcer = PermissionEnforcer(policy)

        assert enforcer.check_tool("search_knowledge_base").allowed
        assert not enforcer.check_tool("deep_research").allowed
        assert "not in allowlist" in enforcer.check_tool("deep_research").reason

    def test_denylist_blocks(self):
        policy = PermissionPolicy(tool_denylist=["deep_research"])
        enforcer = PermissionEnforcer(policy)

        assert not enforcer.check_tool("deep_research").allowed
        assert enforcer.check_tool("search_knowledge_base").allowed

    def test_denylist_overrides_allowlist(self):
        policy = PermissionPolicy(
            tool_allowlist=["deep_research", "search_knowledge_base"],
            tool_denylist=["deep_research"],
        )
        enforcer = PermissionEnforcer(policy)

        assert not enforcer.check_tool("deep_research").allowed
        assert enforcer.check_tool("search_knowledge_base").allowed

    def test_code_execution_blocked(self):
        policy = PermissionPolicy(allow_code_execution=False)
        enforcer = PermissionEnforcer(policy)

        assert not enforcer.check_tool("code_interpreter").allowed
        assert "Code execution" in enforcer.check_tool("code_interpreter").reason


class TestPermissionEnforcerBudget:
    def test_unlimited_budget(self):
        enforcer = PermissionEnforcer(PermissionPolicy())
        assert enforcer.check_budget(100.0).allowed

    def test_per_operation_limit(self):
        policy = PermissionPolicy(budget_per_operation=1.0)
        enforcer = PermissionEnforcer(policy)

        assert enforcer.check_budget(0.50).allowed
        assert not enforcer.check_budget(2.0).allowed

    def test_session_budget(self):
        policy = PermissionPolicy(budget_per_session=5.0)
        enforcer = PermissionEnforcer(policy)

        assert enforcer.check_budget(3.0).allowed
        enforcer.record_spend(3.0)
        assert enforcer.session_spent == 3.0
        assert enforcer.session_remaining == 2.0

        assert not enforcer.check_budget(3.0).allowed
        assert enforcer.check_budget(1.5).allowed


class TestPermissionEnforcerProvider:
    def test_no_restrictions(self):
        enforcer = PermissionEnforcer(PermissionPolicy())
        assert enforcer.check_provider("openai").allowed
        assert enforcer.check_provider("xai", "grok-4.20").allowed

    def test_allowed_providers(self):
        policy = PermissionPolicy(allowed_providers=["openai", "gemini"])
        enforcer = PermissionEnforcer(policy)

        assert enforcer.check_provider("openai").allowed
        assert not enforcer.check_provider("xai").allowed

    def test_blocked_models(self):
        policy = PermissionPolicy(blocked_models=["gpt-4o", "gpt-4o-mini"])
        enforcer = PermissionEnforcer(policy)

        assert enforcer.check_provider("openai", "gpt-5.4").allowed
        assert not enforcer.check_provider("openai", "gpt-4o").allowed


class TestPermissionEnforcerWriteExternal:
    def test_write_allowed_by_default(self):
        enforcer = PermissionEnforcer(PermissionPolicy())
        assert enforcer.check_write().allowed

    def test_write_blocked(self):
        policy = PermissionPolicy(allow_write=False)
        enforcer = PermissionEnforcer(policy)
        assert not enforcer.check_write().allowed

    def test_external_blocked(self):
        policy = PermissionPolicy(allow_external_requests=False)
        enforcer = PermissionEnforcer(policy)
        assert not enforcer.check_external().allowed
