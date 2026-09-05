"""Tests for `deepr capacity probe-plan` - plan-quota backend validation.

The gate is deterministic and $0; the actual vendor round-trip is mocked so these
run with no CLI installed and no spend.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from click.testing import CliRunner

from deepr.backends.capacity import BackendKind, CapacitySource, CostModel
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerEvent,
    QuotaWindowKind,
    load_quota_events,
)
from deepr.backends.quota_snapshot import QuotaSnapshot, QuotaWindowSnapshot
from deepr.cli.commands.capacity import capacity


def _source(
    name: str,
    kind: BackendKind,
    *,
    available: bool = True,
    backend_id: str | None = None,
) -> CapacitySource:
    cost_model = {
        BackendKind.LOCAL: CostModel.OWNED_HARDWARE,
        BackendKind.PLAN_QUOTA: CostModel.CREDIT_POOL,
        BackendKind.API_METERED: CostModel.METERED,
    }[kind]
    return CapacitySource(
        name=name,
        kind=kind,
        cost_model=cost_model,
        available=available,
        backend_id=backend_id or name.lower().replace(" ", "_"),
        detail="test evidence",
    )


_CLEAN = (
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "CODEX_ACCESS_TOKEN",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "ANTIGRAVITY_API_KEY",
    "KIRO_API_KEY",
)
T0 = datetime(2026, 6, 25, 12, tzinfo=UTC)


def _clean_env(monkeypatch):
    for var in _CLEAN:
        monkeypatch.delenv(var, raising=False)


def _stub_probe(monkeypatch, **result):
    async def fake(adapter, *, model=None, **_):
        return {"backend": adapter.backend_id, "reply": "", "latency_ms": 1, "error": "", **result}

    monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", fake)


def _stub_path(monkeypatch, *present):
    installed = set(present)
    monkeypatch.setattr("shutil.which", lambda exe: f"C:/bin/{exe}.exe" if exe in installed else None)


class TestFleet:
    def test_registered(self):
        assert "fleet" in capacity.commands

    def test_human_table_lists_all_backends(self):
        r = CliRunner().invoke(capacity, ["fleet"])
        assert r.exit_code == 0
        for backend in ("codex", "claude", "opencode", "kiro", "grok", "antigravity", "copilot"):
            assert backend in r.output

    def test_json_payload(self):
        r = CliRunner().invoke(capacity, ["fleet", "--json"])
        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["schema_version"] == "deepr-plan-fleet-v1"
        assert payload["contract"]["cost_usd"] == 0.0
        assert len(payload["backends"]) == 7


class TestAdmitPlan:
    def test_registered(self):
        assert "admit-plan" in capacity.commands
        assert "revoke-plan" in capacity.commands

    def test_admit_then_revoke_round_trip(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        for var in _CLEAN:
            monkeypatch.delenv(var, raising=False)
        from deepr.backends.admission import is_admitted

        r = CliRunner().invoke(capacity, ["admit-plan", "claude", "--task-class", "sync"])
        assert r.exit_code == 0, r.output
        assert is_admitted("plan:claude", "sync")

        r2 = CliRunner().invoke(capacity, ["revoke-plan", "claude", "--task-class", "sync"])
        assert r2.exit_code == 0
        assert not is_admitted("plan:claude", "sync")

    def test_gap_fill_task_class_is_admittable(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        for var in _CLEAN:
            monkeypatch.delenv(var, raising=False)
        from deepr.backends.admission import is_admitted

        r = CliRunner().invoke(capacity, ["admit-plan", "claude", "--task-class", "gap_fill"])
        assert r.exit_code == 0, r.output
        assert is_admitted("plan:claude", "gap_fill")

    def test_admit_refuses_reachable_api_key(self, monkeypatch, tmp_path):
        """A credential the dispatch could read still blocks admission."""
        from deepr.backends.plan_quota import safety

        monkeypatch.setattr(safety, "plan_quota_child_env", lambda adapter, env: dict(env))
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-block")
        r = CliRunner().invoke(capacity, ["admit-plan", "claude"])
        assert r.exit_code == 2
        assert "ANTHROPIC_API_KEY" in r.output
        assert "explicitly budgeted API path" in r.output

    def test_admit_allows_held_but_unreachable_api_key(self, monkeypatch, tmp_path):
        """Holding a key for other tools must not deny the $0 path."""
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-held-for-other-tools")
        r = CliRunner().invoke(capacity, ["admit-plan", "claude"])
        assert r.exit_code == 0, r.output

    def test_admit_choice_restricted_to_auto_routable(self):
        """Only a backend with complete execution proof can auto-route."""
        for backend in ("codex", "opencode", "kiro", "grok", "antigravity", "copilot"):
            r = CliRunner().invoke(capacity, ["admit-plan", backend])
            assert r.exit_code != 0, backend

    def test_revoke_when_not_admitted_is_graceful(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        r = CliRunner().invoke(capacity, ["revoke-plan", "codex", "--task-class", "sync"])
        assert r.exit_code == 0
        assert "Nothing to revoke" in r.output


class TestLocalAdmissionGuidance:
    def test_revoke_does_not_claim_automatic_metered_fallback(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        runner = CliRunner()
        admitted = runner.invoke(capacity, ["admit", "qwen-local", "--task-class", "sync", "--yes"])
        assert admitted.exit_code == 0, admitted.output

        revoked = runner.invoke(capacity, ["revoke", "qwen-local", "--task-class", "sync"])

        assert revoked.exit_code == 0, revoked.output
        assert "Local preference removed" in revoked.output
        assert "capacity next" in revoked.output
        assert "falls back" not in revoked.output


class TestCapacityInventoryLanguage:
    def test_human_output_distinguishes_detection_configuration_and_installation(self, capsys):
        from deepr.cli.commands.capacity import _print_sources

        _print_sources(
            [
                _source("Ollama", BackendKind.LOCAL),
                _source("Claude CLI", BackendKind.PLAN_QUOTA, backend_id="claude"),
                _source("OpenAI", BackendKind.API_METERED),
            ]
        )

        output = capsys.readouterr().out
        assert "Capacity sources detected" in output
        assert "used in order" not in output
        assert "Ollama" in output and "detected" in output
        assert "Claude CLI" in output and "installed" in output
        assert "OpenAI" in output and "configured" in output
        assert "Owned/prepaid capacity available" not in output
        assert "capacity next" in output
        assert "capacity fleet" in output

    def test_json_inventory_names_evidence_without_claiming_execution(self):
        from deepr.cli.commands.capacity import _source_to_dict

        plan = _source_to_dict(_source("Claude CLI", BackendKind.PLAN_QUOTA, backend_id="claude"), [])
        local = _source_to_dict(_source("Ollama", BackendKind.LOCAL), [])
        api = _source_to_dict(_source("OpenAI", BackendKind.API_METERED), [])

        assert plan["available"] is True  # compatibility field
        assert plan["availability_basis"] == "installed_on_path"
        assert local["availability_basis"] == "local_runtime_detected"
        assert api["availability_basis"] == "credential_configured"
        assert plan["execution_eligible"] is None
        assert plan["eligibility_command"] == "deepr capacity fleet"
        assert local["eligibility_command"] == "deepr capacity next --task-class sync"
        assert api["eligibility_command"] is None

        cursor = _source("Cursor CLI", BackendKind.PLAN_QUOTA)
        cursor.backend_id = "cursor-agent"
        assert _source_to_dict(cursor, [])["eligibility_command"] is None

    def test_absent_sources_are_deterministically_ineligible(self):
        from deepr.cli.commands.capacity import _source_to_dict

        for kind in BackendKind:
            source = _source(kind.value, kind, available=False)
            payload = _source_to_dict(source, [])
            assert payload["execution_eligible"] is False


class TestProbePlan:
    def test_registered(self):
        assert "probe-plan" in capacity.commands

    def test_reachable_api_key_is_refused_for_probe(self, monkeypatch):
        from deepr.backends.plan_quota import safety

        monkeypatch.setattr(safety, "plan_quota_child_env", lambda adapter, env: dict(env))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-block")
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)
        r = CliRunner().invoke(capacity, ["probe-plan", "claude"])
        assert r.exit_code == 2
        assert "ANTHROPIC_API_KEY" in r.output
        assert "explicitly budgeted API path" in r.output

    def test_held_api_key_does_not_block_probe(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-held-for-other-tools")
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)
        r = CliRunner().invoke(capacity, ["probe-plan", "claude"])
        assert r.exit_code == 0, r.output

    def test_ok_round_trip(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)
        r = CliRunner().invoke(capacity, ["probe-plan", "claude"])
        assert r.exit_code == 0
        assert "OK" in r.output
        assert "plan" in r.output

    def test_failed_round_trip_exits_nonzero(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=False, error="not installed")
        r = CliRunner().invoke(capacity, ["probe-plan", "claude"])
        assert r.exit_code == 1
        assert "FAILED" in r.output

    def test_json_payload(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)
        r = CliRunner().invoke(capacity, ["probe-plan", "claude", "--json"])
        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["backend"] == "claude"
        assert payload["auth_mode"] == "plan"
        assert payload["ok"] is True

    def test_successful_probe_records_usage_observation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)

        r = CliRunner().invoke(capacity, ["probe-plan", "claude", "--json"])

        assert r.exit_code == 0
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].backend_id == "claude"
        assert events[0].event_type == QuotaEventType.USAGE_OBSERVED
        assert events[0].units_used == 1.0
        assert events[0].overage_enabled is None
        assert events[0].detail == "probe-plan successful plan call"

    def test_exhausted_probe_records_exhaustion_observation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=False, error="quota exhausted")

        r = CliRunner().invoke(capacity, ["probe-plan", "claude", "--json"])

        assert r.exit_code == 1
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].backend_id == "claude"
        assert events[0].event_type == QuotaEventType.EXHAUSTED
        assert events[0].detail == "probe-plan exhaustion signature"

    def test_json_failed_overage_proof_is_a_failed_process(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_probe(
            monkeypatch,
            ok=False,
            error="paid extra usage was not proven disabled",
            outcome="overage_guard_refused",
            vendor_dispatched=False,
        )
        result = CliRunner().invoke(capacity, ["probe-plan", "claude", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert payload["outcome"] == "overage_guard_refused"
        assert payload["vendor_dispatched"] is False

    def test_probe_owned_quota_accounting_is_not_duplicated(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        _clean_env(monkeypatch)

        async def accounted_probe(adapter, *, model=None, **_):
            QuotaLedger().record_event(
                QuotaLedgerEvent(
                    backend_id=adapter.backend_id,
                    event_type=QuotaEventType.USAGE_OBSERVED,
                    cost_model=adapter.cost_model,
                    window_kind=adapter.window_kind,
                    units_used=1.0,
                    unit_name=adapter.unit_name,
                    remaining_confidence=QuotaConfidence.UNKNOWN,
                    detail="probe-owned event",
                )
            )
            return {
                "backend": adapter.backend_id,
                "ok": True,
                "reply": "OK",
                "latency_ms": 1,
                "error": "",
                "quota_observation_recorded": True,
            }

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", accounted_probe)

        result = CliRunner().invoke(capacity, ["probe-plan", "claude", "--json"])

        assert result.exit_code == 0
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].detail == "probe-owned event"

    def test_opencode_stored_auth_is_refused_before_probe(self, monkeypatch, tmp_path):
        _clean_env(monkeypatch)
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        async def must_not_probe(*args, **kwargs):
            raise AssertionError("OpenCode probe must not be constructed")

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", must_not_probe)
        result = CliRunner().invoke(capacity, ["probe-plan", "opencode", "--json"])

        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["auth_mode"] == "unknown"
        assert "cannot be proven prepaid or local" in payload["error"]
        assert not (tmp_path / "cost_ledger.jsonl").exists()

    def test_reachable_kiro_api_key_is_refused_before_probe(self, monkeypatch, tmp_path):
        from deepr.backends.plan_quota import safety

        monkeypatch.setattr(safety, "plan_quota_child_env", lambda adapter, env: dict(env))
        _clean_env(monkeypatch)
        monkeypatch.setenv("KIRO_API_KEY", "kiro-validation-key")
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        async def must_not_probe(*args, **kwargs):
            raise AssertionError("Kiro API-key probe must not dispatch")

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", must_not_probe)
        result = CliRunner().invoke(capacity, ["probe-plan", "kiro", "--json"])

        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["auth_mode"] == "metered"
        assert "KIRO_API_KEY" in payload["error"]
        assert not (tmp_path / "cost_ledger.jsonl").exists()

    def test_kiro_still_refused_when_key_is_unreachable(self, monkeypatch, tmp_path):
        """Kiro stays blocked for tool confinement; only the reason moves."""
        _clean_env(monkeypatch)
        monkeypatch.setenv("KIRO_API_KEY", "kiro-validation-key")
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        async def must_not_probe(*args, **kwargs):
            raise AssertionError("Kiro probe must not dispatch")

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", must_not_probe)
        result = CliRunner().invoke(capacity, ["probe-plan", "kiro", "--json"])

        assert result.exit_code == 2
        assert "native read tools" in json.loads(result.output)["error"]
        assert not (tmp_path / "cost_ledger.jsonl").exists()

    def test_metered_backend_fails_closed_before_probe_in_human_mode(self, monkeypatch):
        _clean_env(monkeypatch)

        async def must_not_probe(*args, **kwargs):
            raise AssertionError("metered adapter probe must not be constructed")

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", must_not_probe)
        r = CliRunner().invoke(capacity, ["probe-plan", "copilot"])

        assert r.exit_code == 2
        assert "cannot execute through plan-quota paths" in r.output
        assert "durable reservation" in r.output

    def test_metered_backend_json_and_yes_cannot_bypass_cost_gate(self, monkeypatch):
        _clean_env(monkeypatch)

        async def must_not_probe(*args, **kwargs):
            raise AssertionError("-y must not construct a metered adapter probe")

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", must_not_probe)
        r = CliRunner().invoke(capacity, ["probe-plan", "copilot", "--json", "-y"])

        assert r.exit_code == 2
        payload = json.loads(r.output)
        assert payload["ok"] is False
        assert payload["latency_ms"] == 0
        assert "usage settlement" in payload["error"]


class TestProbeFleet:
    def test_registered(self):
        assert "probe-fleet" in capacity.commands

    def test_explicit_fanout_refuses_blocked_adapter(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        _clean_env(monkeypatch)
        _stub_path(monkeypatch, "claude", "opencode")
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)

        r = CliRunner().invoke(
            capacity,
            ["probe-fleet", "--backend", "claude", "--backend", "opencode", "--json"],
        )

        assert r.exit_code == 1, r.output
        payload = json.loads(r.output)
        assert payload["schema_version"] == "deepr-plan-fleet-probe-v1"
        assert payload["probed_count"] == 2
        assert payload["ok_count"] == 1
        assert payload["failed_count"] == 1
        assert [result["backend"] for result in payload["results"]] == ["claude", "opencode"]
        assert "cannot be proven prepaid or local before dispatch" in payload["results"][1]["error"]
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert [event.backend_id for event in events] == ["claude"]
        assert all(event.event_type == QuotaEventType.USAGE_OBSERVED for event in events)

    def test_default_probes_only_installed_auto_routable_backends(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_path(monkeypatch, "claude", "grok", "agy")
        _stub_probe(monkeypatch, ok=True, reply="OK")

        r = CliRunner().invoke(capacity, ["probe-fleet", "--json"])

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert payload["selected_count"] == 1
        assert payload["results"][0]["backend"] == "claude"

    def test_explicit_unproven_native_tool_backends_are_refused(self, monkeypatch):
        for backend, executable in (
            ("codex", "codex"),
            ("kiro", "kiro-cli"),
            ("grok", "grok"),
            ("antigravity", "agy"),
        ):
            _clean_env(monkeypatch)
            _stub_path(monkeypatch, executable)
            _stub_probe(monkeypatch, ok=True, reply="OK")

            r = CliRunner().invoke(capacity, ["probe-fleet", "--backend", backend, "--json"])

            assert r.exit_code == 1, (backend, r.output)
            payload = json.loads(r.output)
            assert payload["ok_count"] == 0
            assert payload["failed_count"] == 1
            assert [result["backend"] for result in payload["results"]] == [backend]
            assert "execution is disabled" in payload["results"][0]["error"]

    def test_explicit_metered_backend_is_blocked_by_default(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_path(monkeypatch, "copilot")
        _stub_probe(monkeypatch, ok=True, reply="OK")

        r = CliRunner().invoke(capacity, ["probe-fleet", "--backend", "copilot", "--json"])

        assert r.exit_code == 1
        payload = json.loads(r.output)
        assert payload["probed_count"] == 1
        assert payload["failed_count"] == 1
        assert payload["skipped_count"] == 0
        assert payload["results"][0]["status"] == "failed"
        assert "metered at the margin" in payload["results"][0]["error"]

    def test_include_metered_and_yes_cannot_construct_fleet_probe(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_path(monkeypatch, "copilot")

        async def must_not_probe(*args, **kwargs):
            raise AssertionError("compatibility flags must not construct a metered probe")

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", must_not_probe)
        r = CliRunner().invoke(
            capacity,
            ["probe-fleet", "--backend", "copilot", "--include-metered", "-y", "--json"],
        )

        assert r.exit_code == 1
        payload = json.loads(r.output)
        assert payload["probed_count"] == 1
        assert payload["failed_count"] == 1
        assert payload["results"][0]["latency_ms"] == 0
        assert "cost estimation" in payload["results"][0]["error"]

    def test_failure_exits_nonzero_after_payload(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_path(monkeypatch, "claude")
        _stub_probe(monkeypatch, ok=False, error="quota exhausted")

        r = CliRunner().invoke(capacity, ["probe-fleet", "--backend", "claude", "--json"])

        assert r.exit_code == 1
        payload = json.loads(r.output)
        assert payload["failed_count"] == 1
        assert payload["results"][0]["error"] == "quota exhausted"

    def test_opencode_fleet_probe_refuses_before_fanout(self, monkeypatch, tmp_path):
        _clean_env(monkeypatch)
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        _stub_path(monkeypatch, "opencode")

        async def must_not_probe(*args, **kwargs):
            raise AssertionError("OpenCode fleet probe must not dispatch")

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", must_not_probe)
        result = CliRunner().invoke(capacity, ["probe-fleet", "--backend", "opencode", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["failed_count"] == 1
        assert payload["results"][0]["auth_mode"] == "unknown"
        assert "cannot be proven prepaid or local" in payload["results"][0]["error"]
        assert not (tmp_path / "cost_ledger.jsonl").exists()


class TestValidateFleet:
    def test_registered(self):
        assert "validate-fleet" in capacity.commands

    def test_validate_fleet_runs_transport_then_consult(self, monkeypatch, tmp_path):
        from deepr.mcp.consult_validation import MCPConsultValidationCheck, MCPConsultValidationReport

        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        _clean_env(monkeypatch)
        _stub_path(monkeypatch, "claude", "opencode")
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)
        calls: list[tuple[str | None, float]] = []

        async def fake_validation(**kwargs):
            calls.append((kwargs["plan"], kwargs["timeout_seconds"]))
            return MCPConsultValidationReport(
                mode="in_process",
                backend="plan",
                plan=kwargs["plan"],
                question=kwargs["question"],
                requested_experts=kwargs["experts"],
                checks=(MCPConsultValidationCheck("live_consult_call", "passed", "ok"),),
                consult_summary={"trace_id": f"trace-{kwargs['plan']}"},
            )

        monkeypatch.setattr("deepr.mcp.consult_validation.run_in_process_consult_validation", fake_validation)

        r = CliRunner().invoke(
            capacity,
            [
                "validate-fleet",
                "--backend",
                "claude",
                "--backend",
                "opencode",
                "--expert",
                "AI Agent Harnesses",
                "--json",
            ],
        )

        assert r.exit_code == 1, r.output
        payload = json.loads(r.output)
        assert payload["schema_version"] == "deepr-plan-fleet-validation-v1"
        assert payload["contract"]["calls_metered_api"] is False
        assert payload["contract"]["semantic_verdict"] is False
        assert payload["summary"]["ok"] is False
        assert payload["end_to_end_ok_count"] == 1
        assert payload["stages"]["transport"]["ok_count"] == 1
        assert payload["stages"]["consult"]["ok_count"] == 1
        assert payload["stages"]["consult"]["skipped_count"] == 1
        assert payload["summary"]["end_to_end_ok_backends"] == ["claude"]
        assert calls == [("claude", 270.0)]
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert [event.backend_id for event in events] == ["claude"]

    def test_validate_fleet_skips_consult_after_transport_failure(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_path(monkeypatch, "claude")
        _stub_probe(monkeypatch, ok=False, error="quota exhausted")
        calls: list[str | None] = []

        async def fake_validation(**kwargs):
            calls.append(kwargs["plan"])
            raise AssertionError("consult should not run when transport failed")

        monkeypatch.setattr("deepr.mcp.consult_validation.run_in_process_consult_validation", fake_validation)

        r = CliRunner().invoke(capacity, ["validate-fleet", "--backend", "claude", "--json"])

        assert r.exit_code == 1
        payload = json.loads(r.output)
        assert payload["summary"]["ok"] is False
        assert payload["failed_count"] == 1
        assert payload["skipped_count"] == 1
        assert payload["summary"]["failed_transport_backends"] == ["claude"]
        assert payload["summary"]["skipped_consult_plans"] == ["claude"]
        assert "transport failed: quota exhausted" in payload["stages"]["consult"]["results"][0]["error"]["message"]
        assert calls == []

    def test_validate_fleet_refuses_opencode_before_both_stages(self, monkeypatch, tmp_path):
        _clean_env(monkeypatch)
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        _stub_path(monkeypatch, "opencode")

        async def must_not_probe(*args, **kwargs):
            raise AssertionError("OpenCode validation transport must not dispatch")

        async def must_not_consult(**kwargs):
            raise AssertionError("OpenCode validation consult must not dispatch")

        monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", must_not_probe)
        monkeypatch.setattr("deepr.mcp.consult_validation.run_in_process_consult_validation", must_not_consult)

        result = CliRunner().invoke(capacity, ["validate-fleet", "--backend", "opencode", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["stages"]["transport"]["results"][0]["auth_mode"] == "unknown"
        assert payload["summary"]["failed_transport_backends"] == ["opencode"]
        assert payload["summary"]["skipped_consult_plans"] == ["opencode"]
        assert not (tmp_path / "cost_ledger.jsonl").exists()


class TestRefreshQuota:
    def test_registered(self):
        assert "refresh-quota" in capacity.commands

    def test_refresh_quota_records_snapshot(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(backend):
            assert backend == "codex"
            return QuotaSnapshot(
                backend_id="codex",
                display_name="Codex",
                account_id="pro",
                plan="pro",
                cost_model=CostModel.ROLLING_WINDOW,
                windows=(
                    QuotaWindowSnapshot(
                        label="5h",
                        used_fraction=0.25,
                        unit_name="plan_request",
                    ),
                ),
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "codex"])

        assert r.exit_code == 0, r.output
        assert "Codex quota snapshot recorded" in r.output
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].backend_id == "codex"
        assert events[0].units_remaining is None
        assert events[0].metadata["headroom_fraction"] == 0.75

    def test_refresh_quota_accepts_claude_backend(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(backend):
            assert backend == "claude"
            return QuotaSnapshot(
                backend_id="claude",
                display_name="Claude Code",
                account_id="max_20x",
                plan="max_20x",
                cost_model=CostModel.ROLLING_WINDOW,
                windows=(QuotaWindowSnapshot(label="5h", used_fraction=0.4, unit_name="plan_request"),),
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "claude"])

        assert r.exit_code == 0, r.output
        assert "Claude Code quota snapshot recorded" in r.output
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].backend_id == "claude"

    def test_refresh_quota_accepts_grok_backend(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(backend):
            assert backend == "grok"
            return QuotaSnapshot(
                backend_id="grok",
                display_name="Grok Build",
                account_id="dev@example.com",
                plan="SuperGrok",
                cost_model=CostModel.CREDIT_POOL,
                windows=(
                    QuotaWindowSnapshot(
                        label="monthly",
                        window_kind=QuotaWindowKind.MONTHLY_CREDIT_POOL,
                        used_fraction=0.35,
                        unit_name="plan_request",
                    ),
                ),
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "grok"])

        assert r.exit_code == 0, r.output
        assert "Grok Build quota snapshot recorded" in r.output
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].backend_id == "grok"

    def test_refresh_quota_json_payload(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(_backend):
            return QuotaSnapshot(
                backend_id="codex",
                display_name="Codex",
                account_id="pro",
                plan="pro",
                cost_model=CostModel.ROLLING_WINDOW,
                windows=(QuotaWindowSnapshot(label="weekly", used_fraction=0.9),),
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "codex", "--json"])

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert payload["schema_version"] == "deepr-plan-quota-refresh-v1"
        assert payload["backend"] == "codex"
        assert payload["binding_window"] == "weekly"
        assert payload["ledger_event"]["remaining_confidence"] == "vendor_reported"

    def test_refresh_quota_failure_exits_nonzero_and_records_event(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(_backend):
            return QuotaSnapshot(
                backend_id="codex",
                display_name="Codex",
                account_id="unknown",
                cost_model=CostModel.ROLLING_WINDOW,
                ok=False,
                error="no rollout files",
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "codex"])

        assert r.exit_code == 1
        assert "no rollout files" in r.output
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].remaining_confidence.value == "unknown"

    def test_refresh_quota_without_usable_windows_exits_nonzero(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(_backend):
            return QuotaSnapshot(
                backend_id="codex",
                display_name="Codex",
                account_id="pro",
                cost_model=CostModel.ROLLING_WINDOW,
                ok=True,
                windows=(),
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "codex"])

        assert r.exit_code == 1
        assert "no usable quota windows reported" in r.output
