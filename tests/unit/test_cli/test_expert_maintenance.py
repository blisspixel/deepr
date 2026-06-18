"""Characterization + behavior tests for the expert maintenance commands.

These guard the decomposition of experts.py: the sync/absorb commands moved to
deepr/cli/commands/semantic/expert_maintenance.py must stay registered on the
`expert` group with the same options, and gain --local for $0 local execution.
"""

from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert


class TestRegistration:
    def test_sync_registered_with_options(self):
        assert "sync" in expert.commands
        opts = {p.name for p in expert.commands["sync"].params}
        assert {"name", "budget", "dry_run"} <= opts

    def test_absorb_registered_with_options(self):
        assert "absorb" in expert.commands
        opts = {p.name for p in expert.commands["absorb"].params}
        assert {"name", "report_id", "min_confidence", "dry_run"} <= opts

    def test_sync_has_local_and_api_flags(self):
        opts = {p.name for p in expert.commands["sync"].params}
        assert {"local", "api"} <= opts

    def test_absorb_has_local_and_api_flags(self):
        opts = {p.name for p in expert.commands["absorb"].params}
        assert {"local", "api"} <= opts


class TestBackendFlagGuard:
    """--local and --api are mutually exclusive and checked before any store work."""

    def test_sync_rejects_local_and_api_together(self):
        r = CliRunner().invoke(expert, ["sync", "Whoever", "--local", "--api"])
        assert r.exit_code == 2
        assert "not both" in r.output

    def test_absorb_rejects_local_and_api_together(self):
        r = CliRunner().invoke(expert, ["absorb", "Whoever", "job123", "--local", "--api"])
        assert r.exit_code == 2
        assert "not both" in r.output

    def test_sync_local_uses_local_absorber(self, monkeypatch):
        captured = {}
        profile = SimpleNamespace(name="UI Experience Expert")
        client = object()
        research_fn = object()

        class FakeExpertStore:
            def load(self, name):
                assert name == "UI Experience Expert"
                return profile

        class FakeSubscriptionStore:
            subscriptions = [SimpleNamespace(topic="UI/UX for agentic research tools")]

            def __init__(self, name):
                assert name == "UI Experience Expert"

            def due(self):
                return list(self.subscriptions)

        class FakeReportAbsorber:
            def __init__(self, loaded_profile, *, model, client):
                captured["absorber_profile"] = loaded_profile
                captured["absorber_model"] = model
                captured["absorber_client"] = client
                captured["absorber"] = self

        class FakeSyncResult:
            def to_dict(self):
                return {"total_cost": 0.0, "outcomes": []}

        class FakeSyncEngine:
            def __init__(self, loaded_profile, *, research_fn, absorber):
                captured["engine_profile"] = loaded_profile
                captured["research_fn"] = research_fn
                captured["engine_absorber"] = absorber

            async def sync(self, **kwargs):
                captured["sync_kwargs"] = kwargs
                return FakeSyncResult()

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
        monkeypatch.setattr("deepr.experts.sync.ExpertSyncEngine", FakeSyncEngine)
        monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "qwen-local")
        monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: client)
        monkeypatch.setattr(
            "deepr.backends.local.make_local_research_fn",
            lambda model, *, context_builder=None: research_fn,
        )
        monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", FakeReportAbsorber)

        r = CliRunner().invoke(expert, ["sync", "UI Experience Expert", "--local", "-y", "--json"])

        assert r.exit_code == 0
        assert captured["absorber_profile"] is profile
        assert captured["absorber_model"] == "qwen-local"
        assert captured["absorber_client"] is client
        assert captured["engine_profile"] is profile
        assert captured["research_fn"] is research_fn
        assert captured["engine_absorber"] is captured["absorber"]
        assert captured["sync_kwargs"]["budget"] == 2.0
