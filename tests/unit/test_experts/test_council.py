"""Council consultation behavior.

Consult should prefer the expert's stored belief context over a new live agent
loop. The live path remains a fallback for experts with no stored beliefs.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from deepr.core.contracts import ExpertOriginalIdea
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.council import ExpertCouncil, ExpertPerspective
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.profile import ExpertProfile, ExpertStore
from deepr.observability.cost_ledger import CostLedger


@pytest.mark.asyncio
async def test_select_experts_uses_normalized_profile_terms():
    store = ExpertStore()
    store.save(
        ExpertProfile(
            name="AI Agent Harnesses",
            vector_store_id="vs-harness",
            domain="agent harnesses",
            description="agent loop and context engineering for long-running systems",
        )
    )
    store.save(
        ExpertProfile(
            name="AI Cost Optimization",
            vector_store_id="vs-cost",
            domain="cost optimization",
            description="provider billing and cache economics",
        )
    )

    selected = await ExpertCouncil().select_experts("agentic loop context reliability", max_experts=1)

    assert selected == [{"name": "AI Agent Harnesses", "domain": "agent harnesses"}]


@pytest.mark.asyncio
async def test_wide_fanout_drops_zero_overlap_experts():
    """A wide auto-fan-out must stay relevant, not pad with unrelated experts."""
    store = ExpertStore()
    store.save(
        ExpertProfile(
            name="Temporal Knowledge Graphs",
            vector_store_id="vs-tkg",
            domain="temporal graphs",
            description="valid time transaction time bitemporal beliefs",
        )
    )
    store.save(
        ExpertProfile(
            name="Coffee Brewing",
            vector_store_id="vs-coffee",
            domain="coffee",
            description="espresso pourover grind ratio",
        )
    )

    # Ceiling now allows 10, but only one expert overlaps the query.
    selected = await ExpertCouncil().select_experts("bitemporal valid time graphs", max_experts=10)

    assert [exp["name"] for exp in selected] == ["Temporal Knowledge Graphs"]


@pytest.mark.asyncio
async def test_fanout_falls_back_when_nothing_overlaps():
    """If no expert overlaps, consult is still given the available roster, not nothing."""
    store = ExpertStore()
    store.save(
        ExpertProfile(
            name="Coffee Brewing",
            vector_store_id="vs-coffee",
            domain="coffee",
            description="espresso pourover grind ratio",
        )
    )

    selected = await ExpertCouncil().select_experts("quantum chromodynamics lattice", max_experts=10)

    assert [exp["name"] for exp in selected] == ["Coffee Brewing"]


@pytest.mark.asyncio
async def test_consult_uses_stored_beliefs_before_live_session():
    store = BeliefStore("Grounded Cost Expert")
    store.add_belief(
        Belief(
            claim="Prompt caching cost models must separate cache creation tokens from cache read tokens.",
            confidence=0.92,
            evidence_refs=["https://platform.claude.com/docs/en/build-with-claude/prompt-caching"],
            domain="provider economics",
            trust_class="secondary",
        ),
        check_conflicts=False,
    )

    council = ExpertCouncil()
    experts = [{"name": "Grounded Cost Expert", "domain": "provider economics"}]

    with patch("deepr.experts.chat.start_chat_session", side_effect=AssertionError("live session should not start")):
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
            synth.return_value = {"text": "Grounded answer", "agreements": [], "disagreements": [], "cost": 0.001}
            result = await council.consult("How should prompt cache cost be modeled?", experts=experts, budget=1.0)

    perspective = result["perspectives"][0]
    assert perspective["cost"] == 0.0
    assert perspective["context"] == {
        "source": "belief_store",
        "selection": "query_overlap",
        "selection_note": "Selected stored beliefs by query-token overlap, then confidence.",
        "beliefs_available": 1,
        "beliefs_included": 1,
        "matched_terms": ["cache", "cost", "prompt"],
    }
    assert "Stored belief perspective for Grounded Cost Expert." in perspective["response"]
    assert "cache creation tokens" in perspective["response"]
    assert "https://platform.claude.com/docs/en/build-with-claude/prompt-caching" in perspective["response"]


@pytest.mark.asyncio
async def test_consult_context_includes_read_only_self_model_focus():
    ExpertStore().save(
        ExpertProfile(
            name="Self Modeling Consult Expert",
            vector_store_id="vs-self-model",
            domain="agent harnesses",
            installed_skills=["consult-review"],
        )
    )
    store = BeliefStore("Self Modeling Consult Expert")
    store.add_belief(
        Belief(
            claim="Consult traces should carry bounded current-focus metadata.",
            confidence=0.9,
            domain="agent harnesses",
            trust_class="secondary",
        ),
        check_conflicts=False,
    )

    council = ExpertCouncil()
    with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
        synth.return_value = {"text": "Grounded answer", "agreements": [], "disagreements": [], "cost": 0.0}
        result = await council.consult(
            "How should consult traces carry focus?",
            experts=[{"name": "Self Modeling Consult Expert", "domain": "agent harnesses"}],
            budget=1.0,
        )

    self_model = result["perspectives"][0]["context"]["self_model"]
    assert self_model["schema_version"] == "deepr-expert-self-model-v1"
    assert self_model["kind"] == "deepr.expert.self_model"
    assert self_model["status"] == "available"
    assert self_model["contract"]["read_only"] is True
    assert self_model["contract"]["cost_usd"] == 0.0
    assert self_model["current_focus_packet"]["selected_beliefs"][0]["statement"] == (
        "Consult traces should carry bounded current-focus metadata."
    )
    assert "deepr expert why" in self_model["current_focus_packet"]["allowed_tools"]


@pytest.mark.asyncio
async def test_consult_includes_original_ideas_as_labeled_perspective_state():
    tracker = MetaCognitionTracker("Original Idea Council Expert")
    tracker.promote_original_idea_candidate(
        ExpertOriginalIdea.create(
            "Statistical planning before synthesis",
            statement="Expert councils should name random variables, priors, and disconfirming signals.",
            origin="consult trace review",
            rationale="Structured math turns creative advice into verifiable plans.",
            uncertainty="Some domains may not have numeric evidence yet.",
            assumptions=["The synthesis model preserves labeled perspective state."],
            implications=["Host agents can compare candidate plans more rigorously."],
            expected_observations=["Consult artifacts include measurable acceptance criteria."],
            disconfirming_signals=["Reviewers rate the math block as low signal."],
            priority=5,
            confidence=0.82,
        ),
        proposal_id="proposal_original_idea_council",
        evidence_refs=["consult_trace:trace_2"],
    )

    council = ExpertCouncil(allow_live_fallback=False)
    with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
        synth.return_value = {"text": "Original idea synthesis", "agreements": [], "disagreements": [], "cost": 0.0}
        result = await council.consult(
            "How should expert councils plan mathematically?",
            experts=[{"name": "Original Idea Council Expert", "domain": "agent planning"}],
            budget=1.0,
        )

    perspective = result["perspectives"][0]
    assert perspective["confidence"] == 0.82
    assert perspective["context"]["source"] == "perspective_state"
    assert perspective["context"]["selection"] == "original_ideas_only"
    assert perspective["context"]["original_ideas_included"] == 1
    assert perspective["context"]["perspective_state"]["original_ideas"][0]["authority"] == "perspective_state"
    assert "planning inputs, not verified external facts" in perspective["response"]
    assert "random variables, priors, and disconfirming signals" in perspective["response"]


@pytest.mark.asyncio
async def test_consult_uses_high_confidence_fallback_when_query_terms_do_not_match():
    store = BeliefStore("Grounded Harness Expert")
    store.add_belief(
        Belief(
            claim="Long-running agent harnesses need file-backed progress artifacts and incremental checkpoints.",
            confidence=0.91,
            domain="agent harnesses",
            trust_class="secondary",
        ),
        check_conflicts=False,
    )

    council = ExpertCouncil()
    experts = [{"name": "Grounded Harness Expert", "domain": "agent harnesses"}]

    with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
        synth.return_value = {"text": "Fallback answer", "agreements": [], "disagreements": [], "cost": 0.001}
        result = await council.consult("What changed in provider billing?", experts=experts, budget=1.0)

    response = result["perspectives"][0]["response"]
    assert result["perspectives"][0]["context"]["selection"] == "confidence_fallback"
    assert result["perspectives"][0]["context"]["matched_terms"] == []
    assert "No direct stored-belief overlap found" in response
    assert "file-backed progress artifacts" in response


@pytest.mark.asyncio
async def test_consult_marks_live_session_fallback_context():
    class FakeSession:
        cost_accumulated = 0.003

        async def send_message(self, _message):
            return "Live answer"

    council = ExpertCouncil()
    experts = [{"name": "Live Context Expert", "domain": "general"}]

    with patch("deepr.experts.chat.start_chat_session", new_callable=AsyncMock) as start:
        start.return_value = FakeSession()
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
            synth.return_value = {"text": "Live synthesis", "agreements": [], "disagreements": [], "cost": 0.001}
            result = await council.consult("Question without stored beliefs", experts=experts, budget=1.0)

    assert result["perspectives"][0]["context"] == {"source": "live_session"}


@pytest.mark.asyncio
async def test_consult_blocks_live_session_fallback_when_disabled():
    council = ExpertCouncil(allow_live_fallback=False)
    experts = [{"name": "No Stored Context Expert", "domain": "general"}]

    with patch("deepr.experts.chat.start_chat_session", side_effect=AssertionError("live session should not start")):
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
            synth.return_value = {
                "text": "No valid perspectives to synthesise.",
                "agreements": [],
                "disagreements": [],
                "cost": 0.0,
            }
            result = await council.consult("Question without stored beliefs", experts=experts, budget=1.0)

    perspective = result["perspectives"][0]
    assert perspective["confidence"] == 0.0
    assert perspective["cost"] == 0.0
    assert perspective["context"] == {"source": "no_stored_context"}


@pytest.mark.asyncio
async def test_no_context_consult_includes_self_model_when_profile_exists():
    ExpertStore().save(
        ExpertProfile(
            name="No Context Self Model Expert",
            vector_store_id="",
            domain="empty domain",
            installed_skills=[],
        )
    )
    council = ExpertCouncil(allow_live_fallback=False)

    with patch("deepr.experts.chat.start_chat_session", side_effect=AssertionError("live session should not start")):
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
            synth.return_value = {
                "text": "No valid perspectives to synthesise.",
                "agreements": [],
                "disagreements": [],
                "cost": 0.0,
            }
            result = await council.consult(
                "Question without stored beliefs",
                experts=[{"name": "No Context Self Model Expert", "domain": "empty domain"}],
                budget=1.0,
            )

    context = result["perspectives"][0]["context"]
    assert context["source"] == "no_stored_context"
    assert context["self_model"]["schema_version"] == "deepr-expert-self-model-v1"
    assert context["self_model"]["blocked_capability_count"] >= 2
    assert context["self_model"]["current_focus_packet"]["selected_beliefs"] == []


@pytest.mark.asyncio
async def test_synthesis_parser_keeps_disagreements_separate():
    text = """### 1. SYNTHESIS:
Unified answer.

### 2. AGREEMENTS:
- Shared point
- **Callable Role**: Deepr is a callable knowledge role.

### 3. DISAGREEMENTS:
- Divergent point
"""

    class FakeCompletions:
        async def create(self, **kwargs):
            prompt = kwargs["messages"][1]["content"]
            assert "MATH AND STATISTICS" in prompt
            assert "EXECUTION PLAN" in prompt
            assert "DISAGREEMENTS" in prompt
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    with patch("deepr.experts.council.AsyncOpenAI", return_value=fake_client):
        result = await ExpertCouncil()._synthesise(
            "q",
            [ExpertPerspective(expert_name="A", domain="d", response="r")],
            budget=1.0,
        )

    assert result["agreements"] == ["Shared point", "Callable Role: Deepr is a callable knowledge role."]
    assert result["disagreements"] == ["Divergent point"]
    assert result["tokens_input"] == 100
    assert result["tokens_output"] == 50


@pytest.mark.asyncio
async def test_synthesis_injected_local_client_has_zero_cost():
    text = """### SYNTHESIS:
Local answer.

### AGREEMENTS:
- Local agreement
"""

    class FakeCompletions:
        async def create(self, **kwargs):
            assert kwargs["model"] == "qwen-local"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    result = await ExpertCouncil(
        synthesis_client=fake_client,
        synthesis_model="qwen-local",
        synthesis_provider="local",
    )._synthesise(
        "q",
        [ExpertPerspective(expert_name="A", domain="d", response="r")],
        budget=1.0,
    )

    assert result["cost"] == 0.0
    assert result["agreements"] == ["Local agreement"]
    assert result["cost_estimated"] is False


@pytest.mark.asyncio
async def test_anthropic_synthesis_uses_messages_api_and_cache_bucket_costs():
    text = """### SYNTHESIS:
Anthropic answer.

### AGREEMENTS:
- Anthropic agreement
"""
    captured: dict[str, object] = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                id="msg_123",
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text=text)],
                usage=SimpleNamespace(
                    input_tokens=1000,
                    output_tokens=200,
                    cache_creation_input_tokens=300,
                    cache_read_input_tokens=400,
                ),
            )

    fake_client = SimpleNamespace(messages=FakeMessages())

    result = await ExpertCouncil(
        synthesis_client=fake_client,
        synthesis_model="claude-opus-4-8",
        synthesis_provider="anthropic",
    )._synthesise(
        "q",
        [ExpertPerspective(expert_name="A", domain="d", response="r")],
        budget=1.0,
    )

    assert captured["model"] == "claude-opus-4-8"
    assert captured["max_tokens"] == 800
    assert "temperature" not in captured
    assert "top_p" not in captured
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "user"
    assert "MATH AND STATISTICS" in messages[0]["content"]
    assert result["agreements"] == ["Anthropic agreement"]
    assert result["tokens_input"] == 1700
    assert result["tokens_output"] == 200
    assert result["cache_creation_input_tokens"] == 300
    assert result["cache_read_input_tokens"] == 400
    assert result["provider_request_id"] == "msg_123"
    assert result["stop_reason"] == "end_turn"
    assert result["cost"] == 0.012075


@pytest.mark.asyncio
async def test_anthropic_synthesis_without_injected_client_uses_anthropic_client():
    text = """### SYNTHESIS:
Anthropic answer.

### AGREEMENTS:
- Anthropic agreement
"""

    class FakeMessages:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=text)],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )

    fake_client = SimpleNamespace(messages=FakeMessages())

    with (
        patch("deepr.experts.consult.AnthropicConsultSynthesisClient", return_value=fake_client),
        patch("deepr.experts.council.AsyncOpenAI", side_effect=AssertionError("wrong provider client")),
    ):
        result = await ExpertCouncil(
            synthesis_model="claude-opus-4-8",
            synthesis_provider="anthropic",
        )._synthesise(
            "q",
            [ExpertPerspective(expert_name="A", domain="d", response="r")],
            budget=1.0,
        )

    assert result["agreements"] == ["Anthropic agreement"]
    assert result["tokens_input"] == 10
    assert result["tokens_output"] == 5


@pytest.mark.asyncio
async def test_anthropic_synthesis_refusal_fails_closed():
    class FakeMessages:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                stop_reason="refusal",
                stop_details=SimpleNamespace(category="safety"),
                content=[],
                usage=SimpleNamespace(input_tokens=10, output_tokens=0),
            )

    fake_client = SimpleNamespace(messages=FakeMessages())

    result = await ExpertCouncil(
        synthesis_client=fake_client,
        synthesis_model="claude-opus-4-8",
        synthesis_provider="anthropic",
    )._synthesise(
        "q",
        [ExpertPerspective(expert_name="A", domain="d", response="r")],
        budget=1.0,
    )

    assert result["text"] == "Synthesis unavailable."
    assert result["cost"] == 0.0
    assert result["synthesis_status"] == "failed"
    assert result["synthesis_error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_owned_capacity_consult_does_not_reserve_paid_budget(monkeypatch):
    store = BeliefStore("Owned Capacity Consult Expert")
    store.add_belief(
        Belief(
            claim="Owned-capacity consults should stay available even when paid API budget is exhausted.",
            confidence=0.9,
            domain="cost safety",
        ),
        check_conflicts=False,
    )

    class NoPaidReservationManager:
        ABSOLUTE_MAX_PER_OPERATION = 50.0

        def check_and_reserve(self, **_kwargs):
            raise AssertionError("owned-capacity consult should not reserve paid budget")

        def record_cost(self, **_kwargs):
            raise AssertionError("owned-capacity consult should not record paid synthesis cost")

        def refund_reservation(self, _reservation_id):
            raise AssertionError("owned-capacity consult should not create paid reservations")

    monkeypatch.setattr(
        "deepr.experts.cost_safety.get_cost_safety_manager",
        lambda: NoPaidReservationManager(),
    )

    council = ExpertCouncil(synthesis_provider="local", allow_live_fallback=False)
    with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
        synth.return_value = {"text": "Local synthesis", "agreements": [], "disagreements": [], "cost": 0.0}
        result = await council.consult(
            "How should owned consults handle budget gates?",
            experts=[{"name": "Owned Capacity Consult Expert", "domain": "cost safety"}],
            budget=1.0,
        )

    assert result["total_cost"] == 0.0
    assert result["synthesis"] == "Local synthesis"


@pytest.mark.asyncio
async def test_consult_records_synthesis_cost_in_canonical_ledger():
    from deepr.experts.cost_safety import reset_cost_safety_manager

    reset_cost_safety_manager()
    store = BeliefStore("Ledgered Council Expert")
    store.add_belief(
        Belief(
            claim="Council synthesis costs must be recorded in the canonical cost ledger.",
            confidence=0.9,
            domain="cost safety",
        ),
        check_conflicts=False,
    )

    council = ExpertCouncil()
    try:
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
            synth.return_value = {
                "text": "Synthesis",
                "agreements": [],
                "disagreements": [],
                "cost": 0.0025,
                "tokens_input": 123,
                "tokens_output": 45,
            }
            await council.consult(
                "How should council synthesis costs be tracked?",
                experts=[{"name": "Ledgered Council Expert", "domain": "cost safety"}],
                budget=1.0,
            )
    finally:
        reset_cost_safety_manager()

    events = CostLedger().get_events(source="expert_council.synthesis")
    assert len(events) == 1
    event = events[0]
    assert event.operation == "council_synthesis"
    assert event.provider == "openai"
    assert event.cost_usd == 0.0025
    assert event.tokens_input == 123
    assert event.tokens_output == 45


@pytest.mark.asyncio
async def test_consult_records_anthropic_cache_buckets_in_canonical_ledger():
    from deepr.experts.cost_safety import reset_cost_safety_manager

    reset_cost_safety_manager()
    store = BeliefStore("Anthropic Ledgered Council Expert")
    store.add_belief(
        Belief(
            claim="Anthropic cache buckets must be preserved when council synthesis cost is settled.",
            confidence=0.9,
            domain="cost safety",
        ),
        check_conflicts=False,
    )

    council = ExpertCouncil(synthesis_provider="anthropic", synthesis_model="claude-opus-4-8")
    try:
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as synth:
            synth.return_value = {
                "text": "Synthesis",
                "agreements": [],
                "disagreements": [],
                "cost": 0.012075,
                "tokens_input": 1700,
                "tokens_output": 200,
                "cache_creation_input_tokens": 300,
                "cache_read_input_tokens": 400,
                "provider_request_id": "msg_123",
                "stop_reason": "end_turn",
            }
            await council.consult(
                "How should Anthropic cache buckets be tracked?",
                experts=[{"name": "Anthropic Ledgered Council Expert", "domain": "cost safety"}],
                budget=1.0,
            )
    finally:
        reset_cost_safety_manager()

    events = CostLedger().get_events(source="expert_council.synthesis")
    assert len(events) == 1
    event = events[0]
    assert event.provider == "anthropic"
    assert event.model == "claude-opus-4-8"
    assert event.cost_usd == 0.012075
    assert event.tokens_input == 1700
    assert event.tokens_output == 200
    assert event.metadata["cache_creation_input_tokens"] == 300
    assert event.metadata["cache_read_input_tokens"] == 400
    assert event.metadata["provider_request_id"] == "msg_123"
