"""Characterization + behavior tests for the expert maintenance commands.

These guard the decomposition of experts.py: the sync/absorb commands moved to
deepr/cli/commands/semantic/expert_maintenance.py must stay registered on the
`expert` group with the same options, and gain --local for $0 local execution.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.backends.capacity_actions import CAPACITY_NEXT_KIND, CAPACITY_NEXT_SCHEMA_VERSION, CapacityNextAction
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
        assert {"local", "api", "fresh_context", "deep_context", "scheduled"} <= opts

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
            total_cost = 0.0
            outcomes = []

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

        def fake_record_loop_run(**kwargs):
            captured["loop_run_kwargs"] = kwargs
            return SimpleNamespace(to_dict=lambda: {"run_id": "loop_sync_complete"})

        monkeypatch.setattr("deepr.experts.loop_runs.record_loop_run", fake_record_loop_run)

        r = CliRunner().invoke(expert, ["sync", "UI Experience Expert", "--local", "-y", "--json"])

        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["loop_run"]["run_id"] == "loop_sync_complete"
        assert captured["loop_run_kwargs"]["status"].value == "completed"
        assert captured["loop_run_kwargs"]["stop_reason"].value == "no_due_work"
        assert captured["loop_run_kwargs"]["capacity_source"] == "local"
        assert captured["absorber_profile"] is profile
        assert captured["absorber_model"] == "qwen-local"
        assert captured["absorber_client"] is client
        assert captured["engine_profile"] is profile
        assert captured["research_fn"] is research_fn
        assert captured["engine_absorber"] is captured["absorber"]
        assert captured["sync_kwargs"]["budget"] == 2.0

    def test_sync_deep_context_rejects_api(self):
        r = CliRunner().invoke(expert, ["sync", "Whoever", "--api", "--deep-context"])
        assert r.exit_code == 2
        assert "--deep-context is only supported for local sync" in r.output

    def test_sync_fresh_context_requires_local_backend(self, monkeypatch):
        profile = SimpleNamespace(name="UI Experience Expert")

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

        class FakeChoice:
            is_local = False
            reason = "no local admission"

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
        monkeypatch.setattr("deepr.backends.waterfall.choose_maintenance_backend", lambda _task: FakeChoice())

        r = CliRunner().invoke(expert, ["sync", "UI Experience Expert", "--fresh-context", "-y"])

        assert r.exit_code == 2
        assert "requires a local sync backend" in r.output

    def test_scheduled_sync_waits_instead_of_using_metered_backend(self, monkeypatch):
        profile = SimpleNamespace(name="UI Experience Expert")

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

        class FakeChoice:
            is_local = False
            reason = "no local admission"

        class ExplodingSyncEngine:
            def __init__(self, *args, **kwargs):
                raise AssertionError("scheduled wait must not start sync engine")

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
        monkeypatch.setattr("deepr.experts.sync.ExpertSyncEngine", ExplodingSyncEngine)
        monkeypatch.setattr("deepr.backends.waterfall.choose_maintenance_backend", lambda _task: FakeChoice())
        monkeypatch.setattr(
            "deepr.backends.capacity_actions.build_capacity_next_actions",
            lambda **_: [CapacityNextAction(8, "wait", "Wait for cheap capacity", "scheduled wait")],
        )
        monkeypatch.setattr(
            "deepr.experts.loop_runs.record_loop_run",
            lambda **_: SimpleNamespace(to_dict=lambda: {"run_id": "loop_sync"}),
        )

        r = CliRunner().invoke(expert, ["sync", "UI Experience Expert", "--scheduled", "--json"])

        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["status"] == "waiting_for_capacity"
        assert payload["capacity_next"]["schema_version"] == CAPACITY_NEXT_SCHEMA_VERSION
        assert payload["capacity_next"]["kind"] == CAPACITY_NEXT_KIND
        assert payload["capacity_next"]["job_context"]["scheduled"] is True
        assert payload["capacity_next"]["actions"][0]["status"] == "wait"
        assert payload["loop_run"]["run_id"] == "loop_sync"

    def test_scheduled_fresh_context_waits_with_context_preview(self, monkeypatch):
        profile = SimpleNamespace(name="UI Experience Expert")

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

        class FakeChoice:
            is_local = False
            reason = "no local admission"

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
        monkeypatch.setattr("deepr.backends.waterfall.choose_maintenance_backend", lambda _task: FakeChoice())
        monkeypatch.setattr(
            "deepr.backends.capacity_actions.build_capacity_next_actions",
            lambda **_: [CapacityNextAction(8, "wait", "Wait for cheap capacity", "fresh context requires local")],
        )
        monkeypatch.setattr(
            "deepr.experts.loop_runs.record_loop_run",
            lambda **_: SimpleNamespace(to_dict=lambda: {"run_id": "loop_sync"}),
        )

        r = CliRunner().invoke(
            expert,
            ["sync", "UI Experience Expert", "--scheduled", "--fresh-context", "--json"],
        )

        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["status"] == "waiting_for_capacity"
        assert payload["capacity_next"]["schema_version"] == CAPACITY_NEXT_SCHEMA_VERSION
        assert payload["capacity_next"]["kind"] == CAPACITY_NEXT_KIND
        assert payload["capacity_next"]["job_context"]["context_mode"] == "fresh"
        assert payload["capacity_next"]["job_context"]["requires_local"] is True
        assert payload["loop_run"]["run_id"] == "loop_sync"

    def test_scheduled_forced_local_waits_when_no_local_model(self, monkeypatch):
        profile = SimpleNamespace(name="UI Experience Expert")

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

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
        monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: None)
        monkeypatch.setattr(
            "deepr.backends.capacity_actions.build_capacity_next_actions",
            lambda **_: [CapacityNextAction(8, "wait", "Wait for cheap capacity", "start Ollama")],
        )
        monkeypatch.setattr(
            "deepr.experts.loop_runs.record_loop_run",
            lambda **_: SimpleNamespace(to_dict=lambda: {"run_id": "loop_sync"}),
        )

        r = CliRunner().invoke(expert, ["sync", "UI Experience Expert", "--local", "--scheduled", "--json"])

        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["status"] == "waiting_for_capacity"
        assert "running local model" in payload["detail"]
        assert payload["loop_run"]["run_id"] == "loop_sync"

    def test_sync_deep_context_uses_deep_builder(self, monkeypatch):
        captured = {}
        profile = SimpleNamespace(name="UI Experience Expert")
        client = object()
        deep_context_builder = object()
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
            total_cost = 0.0
            outcomes = []

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
        monkeypatch.setattr("deepr.backends.fresh_context.make_free_deep_context_builder", lambda: deep_context_builder)

        def fake_local_research_fn(model, *, context_builder=None):
            captured["research_model"] = model
            captured["context_builder"] = context_builder
            return research_fn

        monkeypatch.setattr("deepr.backends.local.make_local_research_fn", fake_local_research_fn)
        monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", FakeReportAbsorber)

        def fake_record_loop_run(**kwargs):
            captured["loop_run_kwargs"] = kwargs
            return SimpleNamespace(to_dict=lambda: {"run_id": "loop_sync_complete"})

        monkeypatch.setattr("deepr.experts.loop_runs.record_loop_run", fake_record_loop_run)

        r = CliRunner().invoke(expert, ["sync", "UI Experience Expert", "--local", "--deep-context", "-y", "--json"])

        assert r.exit_code == 0
        assert captured["loop_run_kwargs"]["status"].value == "completed"
        assert captured["context_builder"] is deep_context_builder
        assert captured["research_fn"] is research_fn
        assert captured["engine_absorber"] is captured["absorber"]
