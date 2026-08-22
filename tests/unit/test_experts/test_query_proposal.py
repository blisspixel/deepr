from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from deepr.experts.acquisition_plan import (
    ARM_ADVERSARIAL,
    ARM_DESCRIPTIVE,
    ARM_PRIMARY,
    ARM_TERMINOLOGY,
    ARMS,
)
from deepr.experts.query_proposal import assemble_proposed_plan, propose_plan


def test_assemble_proposed_plan_rejects_non_string_queries():
    plan = assemble_proposed_plan(
        {
            "queries": {
                ARM_PRIMARY: [
                    {"query": "OpenTelemetry specification"},
                    42,
                    True,
                    "OpenTelemetry trace context specification",
                ]
            }
        },
        "distributed tracing",
    )

    assert [query.text for query in plan.by_arm(ARM_PRIMARY)] == ["OpenTelemetry trace context specification"]


def test_assemble_proposed_plan_caps_each_arm_and_deduplicates_queries():
    plan = assemble_proposed_plan(
        {
            "queries": {
                ARM_DESCRIPTIVE: [f"observability query number {index}" for index in range(8)],
                ARM_PRIMARY: [
                    "OpenTelemetry trace context specification",
                    "opentelemetry TRACE CONTEXT specification",
                    "W3C distributed tracing recommendation",
                ],
            }
        },
        "distributed tracing",
    )

    assert len(plan.by_arm(ARM_DESCRIPTIVE)) == 4
    assert [query.text for query in plan.by_arm(ARM_PRIMARY)] == [
        "OpenTelemetry trace context specification",
        "W3C distributed tracing recommendation",
    ]


@given(
    st.dictionaries(
        keys=st.sampled_from(ARMS),
        values=st.lists(
            st.one_of(
                st.text(max_size=160),
                st.integers(),
                st.booleans(),
                st.none(),
                st.dictionaries(st.text(max_size=8), st.text(max_size=20), max_size=2),
            ),
            max_size=20,
        ),
    )
)
def test_assemble_proposed_plan_preserves_query_bounds_for_arbitrary_payloads(queries):
    plan = assemble_proposed_plan({"queries": queries}, "distributed tracing")

    assert all(len(plan.by_arm(arm)) <= 4 for arm in ARMS)
    normalized = [query.text.casefold() for query in plan.queries]
    assert len(normalized) == len(set(normalized))
    assert all(isinstance(query.text, str) and query.text for query in plan.queries)


@pytest.mark.asyncio
async def test_propose_plan_does_not_call_completion_for_empty_topic():
    called = False

    async def completion(_prompt: str) -> str:
        nonlocal called
        called = True
        return "{}"

    plan = await propose_plan("  \n ", completion=completion)

    assert called is False
    assert plan.queries == []
    assert plan.fallback_reason == "the topic was empty"


@pytest.mark.asyncio
async def test_propose_plan_does_not_expose_exception_messages():
    async def completion(_prompt: str) -> str:
        raise RuntimeError("provider request failed with sensitive diagnostics")

    plan = await propose_plan("distributed tracing", completion=completion)

    assert plan.fallback_reason == "the query proposal call failed (RuntimeError)"
    assert "sensitive diagnostics" not in plan.fallback_reason


@pytest.mark.asyncio
async def test_propose_plan_accepts_bounded_required_arms():
    async def completion(_prompt: str) -> str:
        return (
            '{"queries": {'
            f'"{ARM_ADVERSARIAL}": ["tail sampling failure analysis"], '
            f'"{ARM_PRIMARY}": ["OpenTelemetry trace context specification"], '
            f'"{ARM_TERMINOLOGY}": ["causal request graph observability"]'
            "}}"
        )

    plan = await propose_plan("  distributed   tracing  ", completion=completion)

    assert plan.topic == "distributed tracing"
    assert plan.fallback_reason == ""
    assert {query.arm for query in plan.queries} == {
        ARM_ADVERSARIAL,
        ARM_PRIMARY,
        ARM_TERMINOLOGY,
    }
