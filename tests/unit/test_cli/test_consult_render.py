"""Terminal answers preserve the same evidence and limits as saved artifacts."""

from copy import deepcopy
from io import StringIO

import pytest
from rich.console import Console

from deepr.cli.consult_render import render_consult


def packet():
    return {
        "answer": "**Use the measured temperature.** " + "Complete advice. " * 110 + "FINAL SENTENCE.",
        "synthesis_status": "completed",
        "cost_usd": 0.0,
        "capacity": {"synthesis_backend": "local", "model": "fixture-model"},
        "context_delivery": {
            "freshness": "stored_context_only",
            "user_prompt": "[1 context block(s) omitted by the prompt limit: Reference. Coverage is incomplete; consult the full artifact.]",
        },
        "perspectives": [
            {
                "expert": "Bread",
                "confidence": 0.75,
                "context": {
                    "studied_at": "2026-10-17",
                    "coverage": "partial",
                    "findings_anchored": 13,
                    "findings_included": 14,
                    "orientation": "Broader knowledge, not established by this study: Yeast strain may matter.",
                    "passages": [
                        {"sha256": "source-id", "origin": "bread.notes", "text": "At 24 C, expect 4 to 5 hours."}
                    ],
                    "positions": [
                        {
                            "question": "When is it ready?",
                            "confidence": "moderate",
                            "confidence_basis": "one note",
                            "would_change_my_mind": "A controlled trial showing the reverse.",
                        }
                    ],
                    "support": [{"question": "When is it ready?", "resolved": False, "study_binding": "unbound"}],
                    "recorded_dissent": ["Sources disagree about doubling."],
                    "unknown": ["Yeast strain."],
                    "live": ["How to measure readiness?"],
                },
            }
        ],
        "agreements": ["Measure the dough."],
        "disagreements": [f"Dissent {n}." for n in range(8)],
    }


@pytest.mark.parametrize("terminal", [False, True])
def test_all_sections_full_answer_narrow_width_and_no_payload_mutation(terminal):
    payload = packet()
    original = deepcopy(payload)
    output = StringIO()
    console = Console(file=output, width=60, force_terminal=terminal, color_system=None)
    render_consult(payload, console)
    text = output.getvalue()
    assert payload == original
    for expected in (
        "Position / Synthesis",
        "Grounds",
        "Support",
        "Currency",
        "Pushback",
        "FINAL SENTENCE.",
        "At 24 C",
        "moderate (recorded label",
        "anchored 13 of 14",
        "studied 2026-10-17",
        "nothing checked live",
        "Sources disagree about doubling.",
        "Dissent 7.",
        "revision condition",
        "study binding unbound",
        "context block(s) omitted",
        "$0.0000 local fixture-model",
        "Knowledge writes: none",
    ):
        assert expected in " ".join(text.split())
    assert text.index("Use the measured temperature.") < text.index("Grounds")
    assert "**" not in text
    assert "75%" not in text
    assert all(len(line) <= 60 for line in text.splitlines())


def test_missing_sections_and_model_truncation_are_explicit():
    output = StringIO()
    render_consult(
        {"answer": "A cut answer", "synthesis_status": "truncated", "synthesis_stop_reason": "length"},
        Console(file=output, width=80),
    )
    text = output.getvalue()
    assert "truncated (length)" in text
    assert "None recorded; this is not proof of consensus." in text
    assert "Freshness: none recorded" in text
    assert "Grounds" in text and "Support" in text


def test_untrusted_rich_markup_is_literal():
    payload = packet()
    payload["perspectives"][0]["expert"] = "[bold]not markup[/bold]"
    output = StringIO()
    render_consult(payload, Console(file=output, width=80))
    assert "[bold]not markup[/bold]" in output.getvalue()
