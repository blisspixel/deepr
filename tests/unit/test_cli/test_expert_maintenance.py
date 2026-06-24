"""Characterization + behavior tests for the expert maintenance commands.

These guard the decomposition of experts.py: the sync/absorb commands moved to
deepr/cli/commands/semantic/expert_maintenance.py must stay registered on the
`expert` group with the same options, and gain --local for $0 local execution.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.backends.capacity_actions import CAPACITY_NEXT_KIND, CAPACITY_NEXT_SCHEMA_VERSION, CapacityNextAction
from deepr.cli.commands.semantic.expert_maintenance import (
    SYNC_CAPACITY_GATE_KIND,
    SYNC_CAPACITY_GATE_SCHEMA_VERSION,
)
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
        assert {"local", "api", "fresh_context", "deep_context", "scheduled", "jitter"} <= opts

    def test_absorb_has_local_and_api_flags(self):
        opts = {p.name for p in expert.commands["absorb"].params}
        assert {"local", "api"} <= opts


class TestBackendFlagGuard:
    """--local and --api are mutually exclusive and checked before any store work."""

    def test_sync_rejects_local_and_api_together(self):
        r = CliRunner().invoke(expert, ["sync", "Whoever", "--local", "--api"])
        assert r.exit_code == 2
        assert "only one of --local, --api, or --plan" in r.output

    def test_sync_rejects_negative_jitter_before_store_work(self, monkeypatch):
        class ExplodingExpertStore:
            def load(self, name):
                raise AssertionError("negative jitter must be rejected before loading experts")

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", ExplodingExpertStore)

        r = CliRunner().invoke(expert, ["sync", "Whoever", "--jitter", "-1"])

        assert r.exit_code == 2
        assert "--jitter must be non-negative" in r.output

    def test_absorb_rejects_local_and_api_together(self):
        r = CliRunner().invoke(expert, ["absorb", "Whoever", "job123", "--local", "--api"])
        assert r.exit_code == 2
        assert "only one of --local, --api, or --plan" in r.output

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

    def test_sync_overlap_lock_records_skip_without_building_engine(self, monkeypatch):
        captured = {}
        profile = SimpleNamespace(name="UI Experience Expert")

        class FakeExpertStore:
            def load(self, name):
                assert name == "UI Experience Expert"
                return profile

        class FakeSubscriptionStore:
            subscriptions = [SimpleNamespace(topic="UI/UX for agentic research tools", budget=1.0)]

            def __init__(self, name):
                assert name == "UI Experience Expert"

            def due(self):
                return list(self.subscriptions)

        @contextmanager
        def fake_lock(name, verb):
            captured["lock"] = (name, verb)
            yield False

        def fake_record_loop_run(**kwargs):
            captured["loop_run_kwargs"] = kwargs
            return SimpleNamespace(
                to_dict=lambda: {
                    "run_id": "loop_locked",
                    "status": kwargs["status"].value,
                    "stop_reason": kwargs["stop_reason"].value,
                }
            )

        def exploding_build_engine(*args, **kwargs):
            raise AssertionError("locked sync must not construct the sync engine")

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
        monkeypatch.setattr("deepr.experts.loop_lock.expert_verb_lock", fake_lock)
        monkeypatch.setattr(
            "deepr.experts.loop_lock.apply_startup_jitter", lambda name, jitter: captured.update(jitter=(name, jitter))
        )
        monkeypatch.setattr("deepr.experts.loop_runs.record_loop_run", fake_record_loop_run)
        monkeypatch.setattr("deepr.experts.maintenance_engine.build_sync_engine", exploding_build_engine)

        r = CliRunner().invoke(
            expert,
            ["sync", "UI Experience Expert", "--api", "--scheduled", "--jitter", "30", "-y", "--json"],
        )

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert captured["jitter"] == ("UI Experience Expert", 30.0)
        assert captured["lock"] == ("UI Experience Expert", "sync")
        assert payload["outcomes"][0]["status"] == "skipped"
        assert payload["outcomes"][0]["detail"] == "another sync for this expert is already running"
        assert payload["loop_run"]["run_id"] == "loop_locked"
        assert payload["loop_run"]["status"] == "waiting"
        assert payload["loop_run"]["stop_reason"] == "overlap_locked"
        assert captured["loop_run_kwargs"]["capacity_source"] == "api_metered"

    def test_sync_deep_context_rejects_api(self):
        r = CliRunner().invoke(expert, ["sync", "Whoever", "--api", "--deep-context"])
        assert r.exit_code == 2
        assert "--deep-context is only supported for local or plan sync" in r.output

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
            is_plan_quota = False
            plan_backend_id = None
            reason = "no local admission"

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
        monkeypatch.setattr("deepr.backends.waterfall.choose_maintenance_backend", lambda _task: FakeChoice())

        r = CliRunner().invoke(expert, ["sync", "UI Experience Expert", "--fresh-context", "-y"])

        assert r.exit_code == 2
        assert "requires a local or plan-quota sync backend" in r.output

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
            is_plan_quota = False
            plan_backend_id = None
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
        assert payload["schema_version"] == SYNC_CAPACITY_GATE_SCHEMA_VERSION
        assert payload["kind"] == SYNC_CAPACITY_GATE_KIND
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
            is_plan_quota = False
            plan_backend_id = None
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
        assert payload["schema_version"] == SYNC_CAPACITY_GATE_SCHEMA_VERSION
        assert payload["kind"] == SYNC_CAPACITY_GATE_KIND
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


class TestPlanQuotaSync:
    """`expert sync --plan <id>` runs the whole sync on prepaid plan capacity,
    behind the deterministic no-surprise-bills gate."""

    def test_sync_has_plan_flags(self):
        opts = {p.name for p in expert.commands["sync"].params}
        assert {"plan", "plan_model"} <= opts

    def _fakes(self, monkeypatch, captured):
        profile = SimpleNamespace(name="Plan Expert")

        class FakeExpertStore:
            def load(self, name):
                return profile

        class FakeSubscriptionStore:
            subscriptions = [SimpleNamespace(topic="t", budget=1.0)]

            def __init__(self, name):
                pass

            def due(self):
                return list(self.subscriptions)

        class FakeSyncResult:
            total_cost = 0.0
            outcomes = []

            def to_dict(self):
                return {"total_cost": 0.0, "outcomes": []}

        class FakeSyncEngine:
            def __init__(self, loaded_profile, *, research_fn=None, absorber=None):
                captured["research_fn"] = research_fn
                captured["absorber"] = absorber

            async def sync(self, **kwargs):
                return FakeSyncResult()

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
        monkeypatch.setattr("deepr.experts.sync.ExpertSyncEngine", FakeSyncEngine)
        return profile

    def test_plan_codex_runs_on_prepaid_and_records_source(self, monkeypatch):
        captured = {}
        research_fn = object()
        chat_client = object()
        self._fakes(monkeypatch, captured)
        for var in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
            monkeypatch.delenv(var, raising=False)

        class FakeReportAbsorber:
            def __init__(self, loaded_profile, *, model, client):
                captured["absorber_model"] = model
                captured["absorber_client"] = client

        monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", FakeReportAbsorber)
        monkeypatch.setattr("deepr.backends.plan_quota.PlanQuotaChatClient", lambda adapter, *, model=None: chat_client)
        monkeypatch.setattr(
            "deepr.backends.plan_quota.make_plan_quota_research_fn",
            lambda adapter, *, model=None, context_builder=None, client=None: research_fn,
        )

        def fake_record_loop_run(**kwargs):
            captured["loop_run_kwargs"] = kwargs
            return SimpleNamespace(to_dict=lambda: {"run_id": "loop_plan"})

        monkeypatch.setattr("deepr.experts.loop_runs.record_loop_run", fake_record_loop_run)

        r = CliRunner().invoke(expert, ["sync", "Plan Expert", "--plan", "codex", "-y", "--json"])

        assert r.exit_code == 0, r.output
        assert captured["research_fn"] is research_fn
        assert captured["absorber_client"] is chat_client
        assert captured["loop_run_kwargs"]["capacity_source"] == "plan_quota:codex"

    def test_auto_routes_to_admitted_plan_backend(self, monkeypatch):
        # The flagship: a plain `sync` (no --plan) auto-routes to a plan backend
        # the waterfall selected because the operator admitted it.
        captured = {}
        research_fn = object()
        chat_client = object()
        self._fakes(monkeypatch, captured)
        for var in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
            monkeypatch.delenv(var, raising=False)

        class PlanChoice:
            is_local = False
            is_plan_quota = True
            plan_backend_id = "codex"
            reason = "plan-quota backend 'codex' (operator-admitted)"

        monkeypatch.setattr("deepr.backends.waterfall.choose_maintenance_backend", lambda _task: PlanChoice())

        class FakeReportAbsorber:
            def __init__(self, loaded_profile, *, model, client):
                captured["absorber_client"] = client

        monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", FakeReportAbsorber)
        monkeypatch.setattr("deepr.backends.plan_quota.PlanQuotaChatClient", lambda adapter, *, model=None: chat_client)
        monkeypatch.setattr(
            "deepr.backends.plan_quota.make_plan_quota_research_fn",
            lambda adapter, *, model=None, context_builder=None, client=None: research_fn,
        )
        monkeypatch.setattr(
            "deepr.experts.loop_runs.record_loop_run",
            lambda **kwargs: (
                captured.update(loop_run_kwargs=kwargs) or SimpleNamespace(to_dict=lambda: {"run_id": "x"})
            ),
        )

        r = CliRunner().invoke(expert, ["sync", "Plan Expert", "-y", "--json"])

        assert r.exit_code == 0, r.output
        assert captured["research_fn"] is research_fn
        assert captured["absorber_client"] is chat_client
        assert captured["loop_run_kwargs"]["capacity_source"] == "plan_quota:codex"

    def test_plan_blocked_when_api_key_present(self, monkeypatch):
        captured = {}
        self._fakes(monkeypatch, captured)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-should-block")

        class ExplodingSyncEngine:
            def __init__(self, *a, **k):
                raise AssertionError("must not run sync when the gate blocks")

        monkeypatch.setattr("deepr.experts.sync.ExpertSyncEngine", ExplodingSyncEngine)

        r = CliRunner().invoke(expert, ["sync", "Plan Expert", "--plan", "codex", "-y"])

        assert r.exit_code == 2
        assert "OPENAI_API_KEY" in r.output
        assert "--api" in r.output

    def test_absorb_has_plan_flags(self):
        opts = {p.name for p in expert.commands["absorb"].params}
        assert {"plan", "plan_model"} <= opts

    def test_absorb_plan_codex_uses_plan_chat_client(self, monkeypatch):
        captured = {}
        profile = SimpleNamespace(name="Plan Expert", total_research_cost=0.0, last_knowledge_refresh=None)
        sentinel_client = object()

        class FakeExpertStore:
            def load(self, name):
                return profile

            def save(self, p):
                captured["saved"] = p

        class FakeIndex:
            def get_report_content(self, report_id, max_chars=0):
                return "report text"

        class FakeResult:
            dry_run = False
            estimated_cost = 0.0

            def to_dict(self):
                return {"absorbed": []}

        class FakeReportAbsorber:
            def __init__(self, loaded_profile, *, model, client=None):
                captured["model"] = model
                captured["client"] = client

            async def absorb(self, *a, **k):
                return FakeResult()

        for var in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.services.context_index.ContextIndex", FakeIndex)
        monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", FakeReportAbsorber)
        monkeypatch.setattr(
            "deepr.backends.plan_quota.PlanQuotaChatClient", lambda adapter, *, model=None: sentinel_client
        )

        r = CliRunner().invoke(expert, ["absorb", "Plan Expert", "job1", "--plan", "codex", "-y", "--json"])

        assert r.exit_code == 0, r.output
        assert captured["client"] is sentinel_client

    def test_absorb_plan_blocked_when_api_key_present(self, monkeypatch):
        profile = SimpleNamespace(name="Plan Expert")

        class FakeExpertStore:
            def load(self, name):
                return profile

        class FakeIndex:
            def get_report_content(self, report_id, max_chars=0):
                return "report text"

        class ExplodingAbsorber:
            def __init__(self, *a, **k):
                raise AssertionError("must not construct absorber when the gate blocks")

        monkeypatch.setenv("OPENAI_API_KEY", "sk-should-block")
        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.services.context_index.ContextIndex", FakeIndex)
        monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", ExplodingAbsorber)

        r = CliRunner().invoke(expert, ["absorb", "Plan Expert", "job1", "--plan", "codex", "-y"])

        assert r.exit_code == 2
        assert "OPENAI_API_KEY" in r.output


class TestAbsorbFromFile:
    """absorb --file ingests a local document at $0 (local) - the repo-docs path."""

    def test_absorb_has_file_option(self):
        opts = {p.name for p in expert.commands["absorb"].params}
        assert "doc_file" in opts

    def test_absorb_rejects_report_id_and_file_together(self, tmp_path):
        doc = tmp_path / "d.md"
        doc.write_text("x", encoding="utf-8")
        r = CliRunner().invoke(expert, ["absorb", "Whoever", "job123", "--file", str(doc)])
        assert r.exit_code == 2
        assert "exactly one of REPORT_ID or --file" in r.output

    def test_absorb_requires_report_id_or_file(self):
        r = CliRunner().invoke(expert, ["absorb", "Whoever"])
        assert r.exit_code == 2
        assert "exactly one of REPORT_ID or --file" in r.output

    def test_absorb_file_reads_doc_and_uses_filename_provenance(self, tmp_path, monkeypatch):
        captured = {}
        profile = SimpleNamespace(name="MCP Expert")
        doc = tmp_path / "mcp-design.md"
        doc.write_text("The Model Context Protocol exposes tools over a registry.", encoding="utf-8")

        class FakeExpertStore:
            def load(self, name):
                return profile

        class FakeResult:
            dry_run = True

            def to_dict(self):
                return {"absorbed": [], "dry_run": True}

        class FakeReportAbsorber:
            def __init__(self, loaded_profile, *, model, client):
                captured["model"] = model
                captured["client"] = client

            async def absorb(self, report_id, report_text, *, min_confidence, dry_run):
                captured["report_id"] = report_id
                captured["report_text"] = report_text
                return FakeResult()

        client = object()
        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", FakeReportAbsorber)
        monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "qwen-local")
        monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: client)

        r = CliRunner().invoke(
            expert, ["absorb", "MCP Expert", "--file", str(doc), "--local", "--dry-run", "-y", "--json"]
        )

        assert r.exit_code == 0, r.output
        # Provenance is the filename, content is the file text, backend is local ($0).
        assert captured["report_id"] == "file:mcp-design.md"
        assert "Model Context Protocol" in captured["report_text"]
        assert captured["model"] == "qwen-local"
        assert captured["client"] is client


class TestLearnWeb:
    """learn-web: live web research on a local model, then absorb - all $0."""

    def test_learn_web_registered_with_options(self):
        assert "learn-web" in expert.commands
        opts = {p.name for p in expert.commands["learn-web"].params}
        assert {"name", "topic", "model", "num_results", "max_pages", "dry_run"} <= opts

    def test_learn_web_runs_research_then_absorbs_local(self, monkeypatch):
        captured = {}
        profile = SimpleNamespace(name="TKG Expert", last_knowledge_refresh=None)

        class FakeExpertStore:
            def load(self, name):
                return profile

            def save(self, p):
                captured["saved"] = p

        async def fake_research(topic, *, model, client, num_results, max_pages):
            captured["research"] = {"topic": topic, "model": model}
            return {
                "answer": f"# {topic}\n\nBody [1].\n\n## Sources\n[1] T - http://a\n",
                "sources": [{"n": 1}],
                "cost": 0.0,
            }

        class FakeResult:
            dry_run = False
            total_candidates = 2
            absorbed = [SimpleNamespace(statement="a current fact", confidence=0.9, outcome="added")]
            rejected = []
            added_count = 1
            merged_count = 0

            def to_dict(self):
                return {"absorbed": 1}

        class FakeReportAbsorber:
            def __init__(self, loaded_profile, *, model, client):
                captured["absorb_model"] = model

            async def absorb(self, report_id, report_text, *, min_confidence, dry_run):
                captured["report_id"] = report_id
                captured["report_text"] = report_text
                return FakeResult()

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.local_research.research_web_local", fake_research)
        monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", FakeReportAbsorber)
        monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "qwen-local")
        monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: object())

        r = CliRunner().invoke(expert, ["learn-web", "TKG Expert", "latest TKG research 2026", "-y"])

        assert r.exit_code == 0, r.output
        assert captured["research"]["topic"] == "latest TKG research 2026"
        assert captured["absorb_model"] == "qwen-local"
        # Provenance marks it as web-sourced; the synthesized report is what gets absorbed.
        assert captured["report_id"] == "web:latest TKG research 2026"
        assert "Sources" in captured["report_text"]
        assert captured.get("saved") is profile  # belief refresh persisted

    def test_learn_web_errors_when_no_report(self, monkeypatch):
        profile = SimpleNamespace(name="TKG Expert")

        class FakeExpertStore:
            def load(self, name):
                return profile

        async def fake_research(topic, *, model, client, num_results, max_pages):
            return {"answer": "", "sources": [], "cost": 0.0, "error": "no web results for topic"}

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
        monkeypatch.setattr("deepr.experts.local_research.research_web_local", fake_research)
        monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "qwen-local")
        monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: object())

        r = CliRunner().invoke(expert, ["learn-web", "TKG Expert", "obscure topic", "-y"])
        assert r.exit_code == 1
        assert "no report" in r.output.lower() or "no web results" in r.output.lower()
