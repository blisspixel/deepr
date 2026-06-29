"""Tests for the temporal perspective MCP server methods.

The query logic itself is covered in tests/unit/test_experts/test_perspective.py;
these tests cover the server-side wrapping: expert lookup, timestamp parsing,
error shapes, and the wiring to a real BeliefStore (on a tmp dir).
"""

from unittest.mock import MagicMock, patch

import pytest

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.mcp.expert_temporal_edges import get_temporal_edges
from deepr.mcp.server import DeeprMCPServer


@pytest.fixture
def server():
    """DeeprMCPServer with mocked collaborators (no network, no filesystem)."""
    with (
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler", return_value=MagicMock()),
    ):
        srv = DeeprMCPServer()
    srv.store = MagicMock()
    return srv


def _real_store(tmp_path) -> BeliefStore:
    return BeliefStore("Perspective Test Expert", storage_dir=tmp_path / "beliefs")


class TestWhatChangedTool:
    @pytest.mark.asyncio
    async def test_expert_not_found(self, server):
        server.store.load.return_value = None
        out = await server.what_changed("Missing Expert", "2026-01-01T00:00:00+00:00")
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_invalid_timestamp(self, server):
        server.store.load.return_value = MagicMock()
        out = await server.what_changed("X", "not-a-timestamp")
        assert out["error_code"] == "INVALID_TIMESTAMP"

    @pytest.mark.asyncio
    async def test_returns_delta_with_added_beliefs(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)
        store.add_belief(
            Belief(claim="MCP hosts should filter tools", confidence=0.9, domain="ai"), check_conflicts=False
        )

        with patch("deepr.experts.beliefs.BeliefStore", return_value=store):
            out = await server.what_changed("Perspective Test Expert", "2020-01-01T00:00:00+00:00")

        assert out["total_changes"] == 1
        assert out["added"][0]["claim"] == "MCP hosts should filter tools"
        assert out["window_truncated"] is False

    @pytest.mark.asyncio
    async def test_changes_before_since_excluded(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)
        store.add_belief(Belief(claim="Old fact", confidence=0.8, domain="ai"), check_conflicts=False)

        with patch("deepr.experts.beliefs.BeliefStore", return_value=store):
            out = await server.what_changed("Perspective Test Expert", "2099-01-01T00:00:00+00:00")

        assert out["total_changes"] == 0


class TestContestedTool:
    @pytest.mark.asyncio
    async def test_expert_not_found(self, server):
        server.store.load.return_value = None
        out = await server.contested("Missing Expert")
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_lists_open_pairs(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)
        existing = Belief(claim="X is true", confidence=0.6, domain="ai")
        store.add_belief(existing, check_conflicts=False)
        store.add_contested_belief(Belief(claim="X is not true", confidence=0.9, domain="ai"), [existing])

        with patch("deepr.experts.beliefs.BeliefStore", return_value=store):
            out = await server.contested("Perspective Test Expert")

        assert out["contested_count"] == 1
        assert out["open_count"] == 1
        assert out["pairs"][0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_empty_store_returns_zero(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)

        with patch("deepr.experts.beliefs.BeliefStore", return_value=store):
            out = await server.contested("Perspective Test Expert")

        assert out["contested_count"] == 0
        assert out["pairs"] == []


class TestExplainBeliefTool:
    @pytest.mark.asyncio
    async def test_expert_not_found(self, server):
        server.store.load.return_value = None
        out = await server.explain_belief("Missing Expert", "anything")
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_belief_not_found(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)
        store.add_belief(Belief(claim="Something specific", confidence=0.8, domain="ai"), check_conflicts=False)

        with patch("deepr.experts.beliefs.BeliefStore", return_value=store):
            out = await server.explain_belief("Perspective Test Expert", "zebra quantum nonsense")

        assert out["error_code"] == "BELIEF_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_explains_with_trajectory_and_contradictions(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)
        target = Belief(
            claim="MCP supports dynamic discovery", confidence=0.7, domain="ai", evidence_refs=["report:abc"]
        )
        store.add_belief(target, check_conflicts=False)
        challenger = Belief(claim="MCP does not support dynamic discovery", confidence=0.9, domain="ai")
        store.add_contested_belief(challenger, [target])

        with patch("deepr.experts.beliefs.BeliefStore", return_value=store):
            out = await server.explain_belief("Perspective Test Expert", target.id, depth=2)

        assert out["belief"]["claim"] == "MCP supports dynamic discovery"
        assert out["evidence_roots"] == ["report:abc"]
        assert [t["change_type"] for t in out["trajectory"]] == ["created"]
        assert len(out["contradicts"]) == 1
        assert out["contradicts"][0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_depth_clamped_to_sane_range(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)
        b = Belief(claim="Depth clamp test", confidence=0.8, domain="ai")
        store.add_belief(b, check_conflicts=False)

        with patch("deepr.experts.beliefs.BeliefStore", return_value=store):
            out = await server.explain_belief("Perspective Test Expert", b.id, depth=99)

        assert out["depth"] == 5  # clamped


class TestTemporalEdgesTool:
    @pytest.mark.asyncio
    async def test_expert_not_found(self, server):
        server.store.load.return_value = None
        out = await get_temporal_edges(server.store, expert_name="Missing Expert")
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_invalid_filter_returns_structured_error(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)

        with patch("deepr.mcp.expert_temporal_edges.BeliefStore", return_value=store):
            out = await get_temporal_edges(server.store, expert_name="Perspective Test Expert", valid_at="not-a-time")

        assert out["error_code"] == "INVALID_TEMPORAL_FILTER"
        assert out["category"] == "validation"

    @pytest.mark.asyncio
    async def test_filters_temporal_edges(self, server, tmp_path):
        server.store.load.return_value = MagicMock()
        store = _real_store(tmp_path)
        source = Belief(claim="Temporal filters are queryable", confidence=0.8, domain="ai")
        target = Belief(claim="Graph commits persist edge qualifiers", confidence=0.8, domain="ai")
        store.add_belief(source, check_conflicts=False)
        store.add_belief(target, check_conflicts=False)
        june = {
            "valid_from": "2026-06-01",
            "valid_until": "2026-06-30",
            "observed_at": "2026-06-29T00:00:00+00:00",
            "temporal_scope": "June 2026",
        }
        july = {
            "valid_from": "2026-07-01",
            "valid_until": "2026-07-31",
            "observed_at": "2026-07-05T00:00:00+00:00",
            "temporal_scope": "July 2026",
        }
        store.add_edge(source.id, target.id, "derived_from", provenance="graph-commit", temporal_context=june)
        store.add_edge(source.id, target.id, "derived_from", provenance="graph-commit", temporal_context=july)

        with patch("deepr.mcp.expert_temporal_edges.BeliefStore", return_value=store):
            out = await get_temporal_edges(
                server.store,
                expert_name="Perspective Test Expert",
                valid_at="2026-06-15T00:00:00+00:00",
                belief_ref="temporal filters",
            )

        assert out["total_edges"] == 1
        assert out["matched_belief"]["belief_id"] == source.id
        assert out["edges"][0]["edge_type"] == "derived_from"
        assert out["edges"][0]["temporal_contexts"] == [june]


class TestExplainBeliefWiring:
    def test_registered_in_search_registry(self):
        from deepr.mcp.search.registry import create_default_registry

        registry = create_default_registry()
        names = {t.name for t in registry.all_tools()}
        assert "deepr_explain_belief" in names
        assert "deepr_temporal_edges" in names

    def test_allowlist_blocks_in_read_only(self):
        from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist

        allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)
        assert allowlist.is_allowed("deepr_explain_belief") is False
        assert allowlist.is_allowed("deepr_temporal_edges") is False
