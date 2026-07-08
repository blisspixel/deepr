"""Property tests for AgentCardGenerator.

Feature: mcp-client-agent-interop
Property: 16
Validates: Requirements 8.2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.a2a.agent_card import AgentCardGenerator, ExpertInfo
from deepr.a2a.constants import CONSULT_SKILL_NAME

# --- Strategies ---

expert_info_st = st.builds(
    ExpertInfo,
    name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
        min_size=1,
        max_size=20,
    ),
    description=st.text(min_size=0, max_size=50),
    domain=st.sampled_from(["infrastructure", "academic", "strategic", "general"]),
)


# --- Property 16: Agent card lists all registered experts ---


def _assert_builtin_consult_skill(skill_name: str, skill_domain: str) -> None:
    assert skill_name == CONSULT_SKILL_NAME
    assert skill_domain == "expert_collaboration"


@settings(max_examples=100)
@given(experts=st.lists(expert_info_st, min_size=0, max_size=10))
def test_agent_card_lists_all_experts(experts: list[ExpertInfo]) -> None:
    """Property 16: Agent card lists all registered experts.

    For any set of registered experts, the generated AgentCard contains
    one skill entry per expert with correct name, description, and domain,
    followed by the built-in multi-expert consult skill.

    **Validates: Requirements 8.2**
    """
    generator = AgentCardGenerator(version="1.0.0")
    generator.register_experts(experts)

    card = generator.generate()

    expected_skill_count = len(experts) + 1
    assert len(card.skills) == expected_skill_count, f"Expected {expected_skill_count} skills, got {len(card.skills)}"

    # Each expert appears as a skill with correct fields
    for i, expert in enumerate(experts):
        skill = card.skills[i]
        assert skill.name == expert.name, f"Skill name mismatch: {skill.name} != {expert.name}"
        assert skill.description == expert.description
        assert skill.domain == expert.domain

    _assert_builtin_consult_skill(card.skills[-1].name, card.skills[-1].domain)


@settings(max_examples=100)
@given(experts=st.lists(expert_info_st, min_size=1, max_size=5))
def test_agent_card_to_dict_contains_all_skills(experts: list[ExpertInfo]) -> None:
    """Agent card dict serialization includes all skills.

    **Validates: Requirements 8.2**
    """
    generator = AgentCardGenerator(version="2.0.0", url="http://localhost:8080")
    generator.register_experts(experts)

    card_dict = generator.to_dict()

    assert card_dict["name"] == "deepr"
    assert card_dict["version"] == "2.0.0"
    expected_skill_count = len(experts) + 1
    assert len(card_dict["skills"]) == expected_skill_count

    for i, expert in enumerate(experts):
        skill_dict = card_dict["skills"][i]
        assert skill_dict["name"] == expert.name
        assert skill_dict["description"] == expert.description
        assert skill_dict["domain"] == expert.domain

    builtin_skill_dict = card_dict["skills"][-1]
    _assert_builtin_consult_skill(builtin_skill_dict["name"], builtin_skill_dict["domain"])
