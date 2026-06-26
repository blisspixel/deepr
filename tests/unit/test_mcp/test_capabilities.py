"""The deepr_capabilities map: a single free discovery call for a consuming agent."""

from __future__ import annotations

from types import SimpleNamespace

from deepr.mcp.capabilities import (
    CAPABILITIES_KIND,
    CAPABILITIES_SCHEMA_VERSION,
    build_capabilities,
)
from deepr.mcp.search.registry import ToolRegistry, ToolSchema


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name, tier in [
        ("deepr_list_experts", "free"),
        ("deepr_consult_experts", "low"),
        ("deepr_agentic_research", "high"),
    ]:
        registry.register(ToolSchema(name=name, description="d", input_schema={}, cost_tier=tier))
    return registry


class _Store:
    def __init__(self, profiles: list[object]) -> None:
        self._profiles = profiles

    def list_all(self) -> list[object]:
        return self._profiles


def test_payload_is_versioned_and_shaped():
    store = _Store([SimpleNamespace(name="Zeta Expert", domain="z"), SimpleNamespace(name="alpha expert", domain="a")])

    caps = build_capabilities(store, _registry(), version="9.9.9")

    assert caps["schema_version"] == CAPABILITIES_SCHEMA_VERSION
    assert caps["kind"] == CAPABILITIES_KIND
    assert caps["server"]["version"] == "9.9.9"
    assert caps["experts"]["count"] == 2
    assert {"free", "low", "medium", "high"} == set(caps["cost_tiers"])
    assert caps["error_contract"]["fields"] == ["error_code", "category", "retryable", "message"]
    assert "local" == caps["zero_cost_synthesis"]["owned"]


def test_roster_is_case_insensitively_sorted():
    store = _Store([SimpleNamespace(name="Zeta Expert", domain="z"), SimpleNamespace(name="alpha expert", domain="a")])

    caps = build_capabilities(store, _registry(), version="1")

    assert [entry["name"] for entry in caps["experts"]["roster"]] == ["alpha expert", "Zeta Expert"]


def test_cost_tiers_come_from_registry_not_hardcoded():
    caps = build_capabilities(_Store([]), _registry(), version="1")

    tiers = {tool["tool"]: tool["cost_tier"] for tool in caps["tools"]}
    assert tiers["deepr_list_experts"] == "free"
    assert tiers["deepr_consult_experts"] == "low"
    assert tiers["deepr_agentic_research"] == "high"


def test_unregistered_key_tools_are_omitted_not_crashing():
    # The minimal registry omits deepr_query_expert; it must be skipped silently.
    caps = build_capabilities(_Store([]), _registry(), version="1")

    names = {tool["tool"] for tool in caps["tools"]}
    assert "deepr_query_expert" not in names
    assert "deepr_list_experts" in names


def test_profile_without_domain_falls_back_to_description():
    store = _Store([SimpleNamespace(name="Doc Expert", domain="", description="docs and IA")])

    caps = build_capabilities(store, _registry(), version="1")

    assert caps["experts"]["roster"][0]["domain"] == "docs and IA"
