"""GPT-5 family chat parameter compatibility (#292 review)."""

from deepr.providers.openai_params import accepts_sampling_params, compatible_chat_kwargs


def test_gpt5_family_drops_sampling_and_renames_legacy_token_limit():
    kwargs = {"model": "gpt-5.6-luna", "temperature": 0.3, "top_p": 0.9, "max_tokens": 200, "max_cost_per_job": 0.05}

    params = compatible_chat_kwargs("gpt-5.6-luna", kwargs)

    assert params == {"model": "gpt-5.6-luna", "max_completion_tokens": 200, "max_cost_per_job": 0.05}
    assert kwargs["temperature"] == 0.3  # input is not mutated


def test_existing_completion_limit_wins_over_legacy_value():
    params = compatible_chat_kwargs("gpt-5.2", {"max_tokens": 10, "max_completion_tokens": 20})
    assert params == {"max_completion_tokens": 20}


def test_other_models_keep_their_parameters():
    kwargs = {"temperature": 0.3, "max_tokens": 500}
    assert compatible_chat_kwargs("qwen3.8:27b", kwargs) == kwargs
    assert accepts_sampling_params("grok-4.3")
    assert not accepts_sampling_params("gpt-5.6-terra")


async def test_task_planner_utility_call_omits_temperature(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from deepr.experts import task_planner as module
    from deepr.experts.constants import UTILITY_MODEL

    captured = {}

    async def fake_execute(**kwargs):
        captured.update(kwargs["request_envelope"])
        return SimpleNamespace()

    monkeypatch.setattr("deepr.services.metered_call.execute_reserved_async_call", fake_execute)
    monkeypatch.setattr("deepr.providers.dispatch_authority.require_official_paid_client", lambda *_: None)
    planner = module.TaskPlanner.__new__(module.TaskPlanner)
    planner.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())))

    await planner._complete_bounded(
        operation="decompose",
        source="test",
        messages=[{"role": "user", "content": "plan"}],
        output_tokens=200,
    )

    assert captured["model"] == UTILITY_MODEL
    assert "temperature" not in captured
    assert 0 < captured["max_completion_tokens"] <= 200
