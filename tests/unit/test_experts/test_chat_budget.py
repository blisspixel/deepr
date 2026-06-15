"""ExpertChatSession budget handling (no-surprise-bills).

Regression for a live-hunt finding (2026-06-14): `budget or 10.0` silently
turned an explicit budget=0.0 ("do not spend") into a $10 ceiling, because 0.0
is falsy. An agent or `--budget 0` caller meaning no spend got a real budget.
"""

from deepr.experts.chat import ExpertChatSession
from deepr.experts.profile import ExpertProfile


def _session(monkeypatch, budget):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    expert = ExpertProfile(name="Budget Probe", vector_store_id="vs-x", domain="ai")
    return ExpertChatSession(expert, budget=budget, enable_router=False)


def test_unspecified_budget_defaults_to_ten(monkeypatch):
    assert _session(monkeypatch, None).budget == 10.0


def test_explicit_zero_budget_is_honored_not_coerced_to_default(monkeypatch):
    # budget=0.0 means "do not spend" - it must NOT become $10.
    assert _session(monkeypatch, 0.0).budget == 0.0


def test_positive_budget_passes_through(monkeypatch):
    assert _session(monkeypatch, 3.5).budget == 3.5
