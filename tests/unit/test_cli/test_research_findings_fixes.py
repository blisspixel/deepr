"""Regression tests for the six live findings from an external agent run
(2026-06-11) plus the pricing drift found in the same sweep.

An agent driving deepr headless hit: a documented --budget flag that did
not exist, a cp1252 help crash, --auto pairing the web-search tool with a
model that rejects it, a zombie QUEUED job after total failure, an explicit
-m silently overridden by routing, and a deprecation warning citing a
retirement date that had already passed without the model retiring.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.cli.commands.run import (
    _mark_job_failed,
    _model_supports_web_search,
    _provider_for_model,
)
from deepr.cli.commands.semantic.research import research
from deepr.cli.main import _ensure_utf8_console
from deepr.routing.deprecation import DEPRECATION_REGISTRY, check_deprecation


class TestBudgetAlias:
    def test_budget_is_an_alias_of_limit(self):
        limit_param = next(p for p in research.params if p.name == "limit")
        opts = set(limit_param.opts) | set(limit_param.secondary_opts)
        assert "--budget" in opts, "README documents --budget; the CLI must accept it"
        assert "--limit" in opts  # back-compat
        assert "-b" in opts and "-l" in opts


class TestWebToolCompatibility:
    def test_nano_models_do_not_get_web_search(self):
        assert _model_supports_web_search("gpt-4.1-nano") is False
        assert _model_supports_web_search("gpt-5.4-nano") is False

    def test_capable_models_keep_web_search(self):
        for model in ("o3-deep-research", "gpt-5.4", "grok-4-3", "gemini-3.1-pro-preview"):
            assert _model_supports_web_search(model) is True


class TestExplicitModelWins:
    def test_provider_resolved_from_registry_for_explicit_model(self):
        assert _provider_for_model("o4-mini-deep-research") == "openai"
        assert _provider_for_model("grok-4-3") == "xai"
        # dotted/hyphenated normalization
        assert _provider_for_model("grok-4.3") == "xai"

    def test_unknown_model_returns_none(self):
        assert _provider_for_model("totally-made-up-model") is None


class TestZombieJobCleanup:
    @pytest.mark.asyncio
    async def test_mark_job_failed_updates_queue(self, monkeypatch):
        calls = {}

        class FakeQueue:
            def __init__(self, db_path):
                calls["db_path"] = db_path

            async def update_status(self, job_id, status, error=None, provider_job_id=None):
                calls["job_id"] = job_id
                calls["status"] = status
                calls["error"] = error
                return True

        import deepr.cli.commands.run as run_mod

        monkeypatch.setattr(run_mod, "SQLiteQueue", FakeQueue)
        await _mark_job_failed("research-abc123", "All providers failed. Last error: boom")

        assert calls["job_id"] == "research-abc123"
        assert calls["db_path"]
        assert calls["status"].name == "FAILED"
        assert "boom" in calls["error"]

    @pytest.mark.asyncio
    async def test_queue_errors_never_mask_the_original_failure(self, monkeypatch):
        class ExplodingQueue:
            def __init__(self, db_path):
                self.db_path = db_path

            async def update_status(self, **kwargs):
                raise RuntimeError("db locked")

        import deepr.cli.commands.run as run_mod

        monkeypatch.setattr(run_mod, "SQLiteQueue", ExplodingQueue)
        await _mark_job_failed("research-abc123", "boom")  # must not raise


class TestUtf8Console:
    def test_reconfigures_streams_on_windows(self, monkeypatch):
        import sys as _sys

        main_mod = _sys.modules["deepr.cli.main"]

        reconfigured = []

        class FakeStream:
            def reconfigure(self, encoding, errors):
                reconfigured.append((encoding, errors))

        monkeypatch.setattr(main_mod.sys, "platform", "win32")
        monkeypatch.setattr(main_mod.sys, "stdout", FakeStream())
        monkeypatch.setattr(main_mod.sys, "stderr", FakeStream())
        _ensure_utf8_console()
        assert reconfigured == [("utf-8", "replace"), ("utf-8", "replace")]

    def test_tolerates_non_reconfigurable_streams(self, monkeypatch):
        import sys as _sys

        main_mod = _sys.modules["deepr.cli.main"]

        monkeypatch.setattr(main_mod.sys, "platform", "win32")
        monkeypatch.setattr(main_mod.sys, "stdout", SimpleNamespace())  # no reconfigure attr
        monkeypatch.setattr(main_mod.sys, "stderr", SimpleNamespace())
        _ensure_utf8_console()  # must not raise


class TestDeprecationTruth:
    def test_o3_deep_research_entry_is_informational_not_dated(self):
        # The 2026-03-26 sunset did not happen (alias live-verified
        # 2026-06-11). A dated entry on the default model warned on every
        # run; the entry must stay informational until a real date exists.
        entry = DEPRECATION_REGISTRY["o3-deep-research"]
        assert entry.sunset_date == ""
        assert "still served" in entry.warning

    def test_check_deprecation_still_resolves_the_entry(self):
        entry = check_deprecation("o3-deep-research")
        assert entry is not None
        assert entry.new_model == "o3-deep-research-2025-06-26"


class TestDeepResearchPricing:
    def test_registry_matches_live_openai_pricing_2026_07_12(self):
        from deepr.providers.registry import get_token_pricing

        # Standard (non-batch) rates from the live pricing page
        o3dr = get_token_pricing("o3-deep-research")
        assert (o3dr["input"], o3dr["output"]) == (5.0, 20.0)
        o4dr = get_token_pricing("o4-mini-deep-research")
        assert (o4dr["input"], o4dr["output"]) == (1.0, 4.0)


class TestBudgetGateNotBypassable:
    """No surprise bills: -y skips confirmation, never the budget gate."""

    def test_yes_flag_cannot_consent_past_the_gate(self, monkeypatch):
        from deepr.cli.commands import run as run_mod
        from deepr.cli.output import OutputContext, OutputMode

        monkeypatch.setattr(run_mod, "check_budget_approval", lambda cost: False)
        ctx = OutputContext(mode=OutputMode.JSON)
        # Previously `yes=True` returned True without consulting the gate.
        assert run_mod._check_budget(yes=True, estimated_cost=5.0, output_context=ctx) is False

    def test_gate_approval_still_passes_headless(self, monkeypatch):
        from deepr.cli.commands import run as run_mod
        from deepr.cli.output import OutputContext, OutputMode

        monkeypatch.setattr(run_mod, "check_budget_approval", lambda cost: True)
        ctx = OutputContext(mode=OutputMode.JSON)
        assert run_mod._check_budget(yes=True, estimated_cost=0.5, output_context=ctx) is True

    def test_monthly_check_uses_canonical_ledger_when_higher(self, monkeypatch, tmp_path):
        from deepr.cli.commands import budget as budget_mod

        # Side counter thinks $0 was spent; the canonical ledger knows $95.
        monkeypatch.setattr(
            budget_mod,
            "load_budget_config",
            lambda: {"monthly_limit": 100, "monthly_spending": 0.0},
        )
        monkeypatch.setattr(budget_mod, "_ledger_month_spend", lambda: 95.0)
        # $95 + $5 = $100 >= 80% of limit -> needs confirmation
        assert budget_mod.check_budget_approval(5.0) is False
        # Small spend well under the threshold still auto-approves
        monkeypatch.setattr(budget_mod, "_ledger_month_spend", lambda: 10.0)
        assert budget_mod.check_budget_approval(5.0) is True

    def test_cautious_mode_has_a_cumulative_ceiling(self, monkeypatch):
        from deepr.cli.commands import budget as budget_mod

        monkeypatch.setattr(budget_mod, "load_budget_config", lambda: {"monthly_limit": 0})
        # Fresh month: small jobs auto-approve
        monkeypatch.setattr(budget_mod, "_ledger_month_spend", lambda: 0.0)
        assert budget_mod.check_budget_approval(0.50) is True
        # Month already at the ceiling: even a $0.99 job needs a human
        monkeypatch.setattr(budget_mod, "_ledger_month_spend", lambda: 25.0)
        assert budget_mod.check_budget_approval(0.99) is False
