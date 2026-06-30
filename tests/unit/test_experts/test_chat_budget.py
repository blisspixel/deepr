"""ExpertChatSession budget handling (no-surprise-bills).

Regression for a live-hunt finding (2026-06-14): `budget or 10.0` silently
turned an explicit budget=0.0 ("do not spend") into a $10 ceiling, because 0.0
is falsy. An agent or `--budget 0` caller meaning no spend got a real budget.
"""

from types import SimpleNamespace

from deepr.experts.chat import ExpertChatSession
from deepr.experts.chat_backends import ExpertChatResult
from deepr.experts.cost_safety import CostSafetyManager, reset_cost_safety_manager
from deepr.experts.profile import ExpertProfile


def _session(monkeypatch, budget):
    reset_cost_safety_manager()
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


def test_session_circuit_breaker_blocks_manager_operations(monkeypatch):
    session = _session(monkeypatch, 1.0)

    for index in range(5):
        session.cost_safety.record_failure(session.session_id, "standard_research", f"failure-{index}")

    allowed, reason, needs_confirmation = session.cost_safety.check_operation(
        session_id=session.session_id,
        operation_type="standard_research",
        estimated_cost=0.002,
        require_confirmation=False,
    )

    assert allowed is False
    assert needs_confirmation is False
    assert reason.startswith("Session circuit breaker open: Too many failures")
    assert session.get_session_summary()["circuit_breaker_open"] is True


async def test_standard_research_reports_blocked_when_session_circuit_is_open(monkeypatch):
    session = _session(monkeypatch, 1.0)

    for index in range(5):
        session.cost_session.record_failure("standard_research", f"failure-{index}")

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("provider fallback should not run when session circuit is open")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)

    result = await session._standard_research("latest ai news")

    assert result["status"] == "blocked"
    assert result["mode"] == "standard_research"
    assert result["error"].startswith("Research blocked: Session circuit breaker open")


async def test_deep_research_reports_blocked_when_session_budget_is_exhausted(monkeypatch):
    session = _session(monkeypatch, 0.0)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("deep research provider call should not run after budget denial")

    monkeypatch.setattr(session.client.responses, "create", fail_if_called)
    monkeypatch.setattr(CostSafetyManager, "ABSOLUTE_MAX_PER_OPERATION", 10.0)

    result = await session._deep_research("design a migration strategy")

    assert result["status"] == "blocked"
    assert result["mode"] == "deep_research"
    assert result["session_budget"] == 0.0
    assert result["error"].startswith("Session budget exceeded: Insufficient budget")


async def test_first_chat_generation_is_preflight_budget_checked(monkeypatch):
    session = _session(monkeypatch, 0.0)
    session.should_use_tot = lambda _query: False

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("chat provider call should not run after budget denial")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)

    result = await session.send_message("What should this expert improve next?")

    assert result.startswith("Chat blocked: Insufficient budget")
    assert session.reasoning_trace[-1]["step"] == "chat_generation_budget"
    assert session.reasoning_trace[-1]["allowed"] is False


async def test_first_chat_generation_uses_chat_backend(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.should_use_tot = lambda _query: False
    captured = []

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy client should be behind chat_backend")

    class FakeBackend:
        async def complete(self, request):
            captured.append(request)
            return ExpertChatResult(
                message=SimpleNamespace(content="backend answer", tool_calls=[]),
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            )

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    session.chat_backend = FakeBackend()

    result = await session.send_message("What should this expert improve next?")

    assert result == "backend answer"
    assert len(captured) == 1
    assert captured[0].model == session.expert.model
    assert captured[0].tool_choice == "auto"
    assert captured[0].messages[0]["role"] == "system"


async def test_streaming_first_chat_generation_is_preflight_budget_checked(monkeypatch):
    session = _session(monkeypatch, 0.0)
    session.should_use_tot = lambda _query: False

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("streaming chat provider call should not run after budget denial")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)

    result = await session.send_message_streaming("What should this expert improve next?")

    assert result.startswith("Chat blocked: Insufficient budget")
    assert session.reasoning_trace[-1]["step"] == "chat_generation_budget"
    assert session.reasoning_trace[-1]["allowed"] is False
