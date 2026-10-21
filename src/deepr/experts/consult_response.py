"""Admit a narrow literal response format and check its visible word count.

This is a form boundary, not a semantic reviewer. It neither clips an answer
nor dispatches another completion. Natural-language requirements outside the
explicit supported directive remain instructions for the model and review.
"""

from __future__ import annotations

import re
from typing import Any

_DIRECTIVE = re.compile(r"(?:^|(?<=[.!?])\s+)(?P<directive>Answer in at most (?P<max_words>[1-9][0-9]{0,4}) words\.)$")
_OTHER_WORD_REQUEST = re.compile(r"\bwords?\b", re.IGNORECASE)
_COUNTING_RULE = "visible-whitespace-tokens-v1"


def response_form_contract(question: str) -> dict[str, Any]:
    """Recognize only a final positive literal sentence outside quoted text.

    Quotes, code, any other word-count reference, or an unsupported spelling
    decline automatic admission. This deliberately does not interpret arbitrary
    language, negation, approximate limits, minimums or quoted instructions.
    The original question is always retained for the model and the reviewer.
    """
    contract: dict[str, Any] = {
        "kind": "deepr.response-form.v1",
        "counting_rule": _COUNTING_RULE,
        "admission": "not_admitted",
        "max_words": None,
        "semantic_preservation": "unassessed",
    }
    question = question.rstrip()
    match = _DIRECTIVE.search(question)
    if match is None or any(char in question for char in ('"', "'", "`", "\u2018", "\u2019", "\u201c", "\u201d")):
        return contract
    prefix = question[: match.start("directive")]
    line_prefix = prefix.rsplit("\n", 1)[-1]
    if "~~~" in question or (not line_prefix.strip() and (line_prefix.startswith("    ") or "\t" in line_prefix)):
        return contract
    if _OTHER_WORD_REQUEST.search(prefix):
        return contract
    contract.update(
        admission="admitted", max_words=int(match.group("max_words")), origin="literal_final_question_directive"
    )
    return contract


def response_form_instruction(contract: dict[str, Any]) -> str:
    if contract["admission"] != "admitted":
        return ""
    return (
        f"Response form: at most {contract['max_words']} whitespace-separated words in the complete visible answer, "
        "including headings and caveats. Keep the supported answer, applicable conditions and material uncertainty "
        "within that bound; omit repetition and irrelevant detail.\n\n"
    )


def admit_response_form(question: str, synthesis: dict[str, Any]) -> dict[str, Any]:
    """Retain the actual draft and accounting, separating form from meaning."""
    form = response_form_contract(question)
    form["actual_words"] = len(str(synthesis.get("text", "")).split())
    form["status"] = "not_checked"
    if form["admission"] == "admitted":
        form["status"] = "met" if form["actual_words"] <= form["max_words"] else "exceeded"
        if form["status"] == "exceeded" and synthesis.get("synthesis_status") == "completed":
            synthesis["synthesis_status"] = "failed"
            synthesis["synthesis_error_type"] = "ResponseWordLimit"
    return {**synthesis, "response_form": form}
