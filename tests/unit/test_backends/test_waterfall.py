"""Tests for deepr.backends.waterfall - backend selection ($0, no I/O).

``available_models_fn`` and the admissions ``path``/``now`` are injected, so
these exercise the full waterfall logic with no Ollama and no real ledger.
Selection is admission-driven: an admitted model is used only if it is also
currently available.
"""

from __future__ import annotations

from datetime import UTC, datetime

from deepr.backends.admission import record_admission
from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerEvent,
    QuotaWindowKind,
)
from deepr.backends.waterfall import (
    BACKEND_API_METERED,
    BACKEND_LOCAL,
    BACKEND_PLAN_QUOTA,
    choose_maintenance_backend,
    choose_plan_quota_backend,
)

T0 = datetime(2026, 6, 13, tzinfo=UTC)


def _fake_which(*present):
    found = set(present)
    return lambda exe: f"/usr/bin/{exe}" if exe in found else None


def _record_observed_quota(path, backend_id="codex", *, remaining=100.0, exhausted=False):
    QuotaLedger(path).record_event(
        QuotaLedgerEvent(
            backend_id=backend_id,
            event_type=QuotaEventType.EXHAUSTED if exhausted else QuotaEventType.WINDOW_OBSERVED,
            cost_model=CostModel.ROLLING_WINDOW,
            window_kind=QuotaWindowKind.ROLLING_5H,
            units_remaining=remaining,
            unit_name="plan_request",
            remaining_confidence=QuotaConfidence.OBSERVED,
            overage_enabled=False,
        )
    )


def _choose(task_class, *, available, path, now=T0):
    return choose_maintenance_backend(
        task_class, now=now, available_models_fn=lambda: list(available), admissions_path=path
    )


class TestChoose:
    def test_nothing_admitted_falls_to_metered(self, tmp_path):
        choice = _choose("sync", available=["llama3.1"], path=tmp_path / "a.jsonl")
        assert choice.backend == BACKEND_API_METERED
        assert not choice.is_local
        assert "no local model admitted" in choice.reason

    def test_admitted_but_ollama_unreachable(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.8, now=T0, path=p)
        choice = _choose("sync", available=[], path=p)
        assert choice.backend == BACKEND_API_METERED
        assert "not reachable" in choice.reason

    def test_admitted_but_model_not_loaded(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.8, now=T0, path=p)
        # Ollama is up but serving a different model.
        choice = _choose("sync", available=["other-model"], path=p)
        assert choice.backend == BACKEND_API_METERED
        assert "unavailable" in choice.reason

    def test_admitted_and_available_is_chosen(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.8, now=T0, path=p)
        choice = _choose("sync", available=["llama3.1", "other"], path=p)
        assert choice.backend == BACKEND_LOCAL
        assert choice.is_local
        assert choice.model == "llama3.1"
        assert "quality 0.800 clears floor 0.700" in choice.reason
        assert "owned capacity before metered API" in choice.reason

    def test_scoreless_admission_does_not_auto_route(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", now=T0, path=p)
        choice = _choose("sync", available=["llama3.1"], path=p)
        assert choice.backend == BACKEND_API_METERED
        assert "unknown" in choice.reason

    def test_low_score_admission_does_not_auto_route(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.6, now=T0, path=p)
        choice = _choose("sync", available=["llama3.1"], path=p)
        assert choice.backend == BACKEND_API_METERED
        assert "below_floor" in choice.reason

    def test_admission_is_task_class_scoped(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.8, now=T0, path=p)
        assert _choose("absorb", available=["llama3.1"], path=p).backend == BACKEND_API_METERED
        assert _choose("sync", available=["llama3.1"], path=p).backend == BACKEND_LOCAL

    def test_env_pref_breaks_tie_among_admitted(self, tmp_path, monkeypatch):
        p = tmp_path / "a.jsonl"
        record_admission("model-a", "absorb", score=0.9, now=T0, path=p)
        record_admission("model-b", "absorb", score=0.8, now=T0, path=p)
        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "model-b")
        choice = _choose("absorb", available=["model-a", "model-b"], path=p)
        assert choice.model == "model-b"

    def test_env_pref_ignored_when_not_admitted(self, tmp_path, monkeypatch):
        p = tmp_path / "a.jsonl"
        record_admission("model-a", "absorb", score=0.8, now=T0, path=p)
        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "not-admitted")
        choice = _choose("absorb", available=["model-a", "not-admitted"], path=p)
        # Falls back to the admitted+available one, not the env pref.
        assert choice.model == "model-a"

    def test_env_pref_ignored_when_it_fails_quality(self, tmp_path, monkeypatch):
        p = tmp_path / "a.jsonl"
        record_admission("model-a", "absorb", score=0.8, now=T0, path=p)
        record_admission("model-b", "absorb", score=0.6, now=T0, path=p)
        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "model-b")
        choice = _choose("absorb", available=["model-a", "model-b"], path=p)
        assert choice.model == "model-a"


class TestExplicitPlanQuota:
    def test_clean_env_resolves_to_plan(self):
        choice = choose_plan_quota_backend("codex", env={})
        assert choice.backend == BACKEND_PLAN_QUOTA
        assert choice.is_plan_quota
        assert choice.plan_backend_id == "codex"

    def test_api_key_present_falls_to_metered(self):
        choice = choose_plan_quota_backend("codex", env={"OPENAI_API_KEY": "sk-x"})
        assert choice.backend == BACKEND_API_METERED
        assert "OPENAI_API_KEY" in choice.reason

    def test_unknown_backend_falls_to_metered(self):
        choice = choose_plan_quota_backend("bogus", env={})
        assert choice.backend == BACKEND_API_METERED
        assert "unknown" in choice.reason


class TestPlanQuotaAutoRung:
    def _auto(self, *, which, path, plan_env=None):
        return choose_maintenance_backend(
            "sync",
            now=T0,
            available_models_fn=lambda: [],  # no local
            admissions_path=path / "adm.jsonl",
            which=which,
            plan_env=plan_env if plan_env is not None else {},
            quota_ledger_path=path / "quota.jsonl",
        )

    def test_not_installed_falls_to_metered(self, tmp_path):
        choice = self._auto(which=_fake_which(), path=tmp_path)
        assert choice.backend == BACKEND_API_METERED

    def test_installed_but_no_observed_quota_stays_off(self, tmp_path):
        # The honest default: a CLI can't report remaining quota, so it is NOT
        # auto-routed even when installed and authenticated in plan mode.
        choice = self._auto(which=_fake_which("codex"), path=tmp_path)
        assert choice.backend == BACKEND_API_METERED

    def test_observed_remaining_quota_enables_auto_route(self, tmp_path):
        _record_observed_quota(tmp_path / "quota.jsonl", "codex", remaining=120.0)
        choice = self._auto(which=_fake_which("codex"), path=tmp_path)
        assert choice.backend == BACKEND_PLAN_QUOTA
        assert choice.plan_backend_id == "codex"

    def test_exhausted_quota_stays_metered(self, tmp_path):
        _record_observed_quota(tmp_path / "quota.jsonl", "codex", exhausted=True)
        choice = self._auto(which=_fake_which("codex"), path=tmp_path)
        assert choice.backend == BACKEND_API_METERED

    def test_api_key_env_blocks_auto_route(self, tmp_path):
        _record_observed_quota(tmp_path / "quota.jsonl", "codex", remaining=120.0)
        choice = self._auto(which=_fake_which("codex"), path=tmp_path, plan_env={"OPENAI_API_KEY": "sk-x"})
        assert choice.backend == BACKEND_API_METERED

    def test_metered_at_margin_cli_not_auto_routed(self, tmp_path):
        # copilot is installed + has observed quota, but it's metered-per-use,
        # so it is never auto-routed (enabled_by_default=False).
        _record_observed_quota(tmp_path / "quota.jsonl", "copilot", remaining=120.0)
        choice = self._auto(which=_fake_which("copilot"), path=tmp_path)
        assert choice.backend == BACKEND_API_METERED
