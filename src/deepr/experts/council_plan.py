"""Propose diverse expert councils for a goal or project text ($0 structure).

Model composition is optional (local/plan). Diversity axis coverage is a
deterministic gate - see docs/design/diverse-expert-council.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

COUNCIL_PLAN_SCHEMA = "deepr-expert-council-plan-v1"
COUNCIL_PLAN_KIND = "deepr.expert.council_plan"

# Deterministic diversity axes (ids are stable for tests and gates).
DIVERSITY_AXES: tuple[dict[str, str], ...] = (
    {
        "id": "domain_practitioner",
        "label": "Domain practitioner",
        "protects": "Missing core technical truth for the problem domain",
    },
    {
        "id": "adversary_red_team",
        "label": "Adversary / red team",
        "protects": "Missing abuse cases, threat model, failure under attack",
    },
    {
        "id": "ops_reliability",
        "label": "Ops / reliability",
        "protects": "Missing degraded mode, runbooks, observability, recovery",
    },
    {
        "id": "standards_institutional",
        "label": "Standards / institutional",
        "protects": "Missing regulation, carrier-grade, compliance, org reality",
    },
    {
        "id": "extreme_end_user",
        "label": "Extreme end-user / field",
        "protects": "Missing off-lab UX, hostile environment, non-expert operators",
    },
    {
        "id": "scientific_rigor",
        "label": "Scientific rigor",
        "protects": "Missing evaluation, overclaim, unfalsifiable marketing",
    },
    {
        "id": "economic_adoption",
        "label": "Economic / adoption",
        "protects": "Missing who pays, who runs it, who abandons it",
    },
    {
        "id": "historical_lineage",
        "label": "Historical / prior art",
        "protects": "Missing prior art and known dead ends",
    },
)

_MIN_AXES = 4
_DEFAULT_ROLE_COUNT = 5
_MAX_ROLE_COUNT = 8


@dataclass
class CouncilRole:
    name: str
    domain_description: str
    axis: str
    perspective_lens: str
    dissent_style: str
    make_description: str
    deepen_query: str
    existing_expert: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExpertCouncilPlan:
    schema_version: str = COUNCIL_PLAN_SCHEMA
    kind: str = COUNCIL_PLAN_KIND
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    goal: str = ""
    composition_mode: str = "scaffold"  # scaffold | local_model | plan
    axes_required_min: int = _MIN_AXES
    axes_covered: list[str] = field(default_factory=list)
    diversity_ok: bool = False
    roles: list[dict[str, Any]] = field(default_factory=list)
    consult_prompt: str = ""
    next_operator_steps: list[str] = field(default_factory=list)
    capacity_notes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            "# Expert council plan",
            "",
            f"Generated: {self.generated_at}",
            f"Composition mode: `{self.composition_mode}`",
            f"Diversity gate: {'PASS' if self.diversity_ok else 'FAIL'} "
            f"(axes covered {len(self.axes_covered)} / min {self.axes_required_min})",
            "",
            "## Goal",
            "",
            self.goal.strip() or "(empty)",
            "",
            "## Axes covered",
            "",
        ]
        for axis_id in self.axes_covered:
            label = next((a["label"] for a in DIVERSITY_AXES if a["id"] == axis_id), axis_id)
            lines.append(f"- `{axis_id}` - {label}")
        lines += ["", "## Roster", ""]
        for i, role in enumerate(self.roles, 1):
            lines += [
                f"### {i}. {role.get('name', 'role')}",
                "",
                f"- **Axis:** `{role.get('axis')}`",
                f"- **Domain:** {role.get('domain_description')}",
                f"- **Lens:** {role.get('perspective_lens')}",
                f"- **Dissent:** {role.get('dissent_style')}",
                f"- **Deepen query:** {role.get('deepen_query')}",
            ]
            if role.get("existing_expert"):
                lines.append(f"- **Reuse existing:** {role['existing_expert']}")
            lines += [
                "",
                "```text",
                f'deepr expert make "{role.get("name")}" --local -d "{role.get("make_description")}"',
                f'deepr expert deepen-plan "{role.get("name")}" --query "{role.get("deepen_query")}"',
                "```",
                "",
            ]
        lines += [
            "## Challenge consult prompt",
            "",
            self.consult_prompt.strip(),
            "",
            "## Operator steps (order)",
            "",
        ]
        for i, step in enumerate(self.next_operator_steps, 1):
            lines.append(f"{i}. {step}")
        lines += ["", "## Capacity", ""]
        for note in self.capacity_notes:
            lines.append(f"- {note}")
        lines += ["", "## Limitations", ""]
        for lim in self.limitations:
            lines.append(f"- {lim}")
        lines.append("")
        return "\n".join(lines)


def _axes_by_id() -> dict[str, dict[str, str]]:
    return {a["id"]: a for a in DIVERSITY_AXES}


def validate_diversity(roles: list[dict[str, Any]], *, min_axes: int = _MIN_AXES) -> tuple[bool, list[str]]:
    """Deterministic diversity gate: enough distinct axes, no empty names."""
    covered: list[str] = []
    for role in roles:
        axis = str(role.get("axis") or "").strip()
        name = str(role.get("name") or "").strip()
        if not name or not axis:
            return False, covered
        if axis in _axes_by_id() and axis not in covered:
            covered.append(axis)
    return len(covered) >= min_axes, covered


def _scaffold_roles(goal: str, *, count: int) -> list[dict[str, Any]]:
    """Structural diverse roster when no model is available."""
    goal_short = re.sub(r"\s+", " ", goal.strip())[:120] or "the project"
    # Prefer a fixed diverse subset for review-style goals.
    preferred = [
        "domain_practitioner",
        "adversary_red_team",
        "ops_reliability",
        "standards_institutional",
        "extreme_end_user",
        "scientific_rigor",
        "economic_adoption",
        "historical_lineage",
    ]
    axis_ids = preferred[: max(_MIN_AXES, min(count, _MAX_ROLE_COUNT))]
    templates = {
        "domain_practitioner": (
            "Domain Practitioner",
            f"Practitioner of the core technical domain for: {goal_short}",
            "Reads for technical correctness, missing primitives, and implementability.",
            "Attacks hand-wavy architecture and unproven greenfield claims.",
            f"core technology latest documentation practices failures for {goal_short}",
        ),
        "adversary_red_team": (
            "Adversary Red Team Analyst",
            f"Security and adversary modeling for systems like: {goal_short}",
            "Reads for abuse cases, privilege, crypto theater, and hostile operators.",
            "Attacks optimistic threat models and missing fail-closed defaults.",
            f"threat modeling attack surface abuse cases for {goal_short}",
        ),
        "ops_reliability": (
            "Operations Reliability Engineer",
            f"Production operations and degraded-mode reliability for: {goal_short}",
            "Reads for runbooks, observability, recovery, and day-2 operations.",
            "Attacks lab-only demos that cannot survive partial failure.",
            f"SRE runbooks failure modes observability for {goal_short}",
        ),
        "standards_institutional": (
            "Institutional Standards Architect",
            f"Standards, carrier/regulatory, or institutional constraints for: {goal_short}",
            "Reads for standards fit, compliance, and multi-vendor reality.",
            "Attacks claims that ignore institutional or standards constraints.",
            f"standards compliance institutional constraints for {goal_short}",
        ),
        "extreme_end_user": (
            "Extreme Field User",
            f"Field or extreme-environment user of: {goal_short}",
            "Reads for off-lab UX, stress, power, skill, and chaos constraints.",
            "Attacks ivory-tower designs that fail when infrastructure is gone.",
            f"field deployment off-grid user experience failure for {goal_short}",
        ),
        "scientific_rigor": (
            "Computer Science Research Reviewer",
            f"Research-methods and evaluation rigor for claims about: {goal_short}",
            "Reads for falsifiability, evaluation, and overclaim.",
            "Attacks marketing language dressed as research results.",
            f"evaluation methodology prior art claims for {goal_short}",
        ),
        "economic_adoption": (
            "Adoption Economics Analyst",
            f"Who funds, runs, and abandons systems like: {goal_short}",
            "Reads for incentives, TCO, and realistic operators.",
            "Attacks designs nobody will operate or pay for.",
            f"adoption economics operators TCO for {goal_short}",
        ),
        "historical_lineage": (
            "Prior Art Historian",
            f"Historical lineage and failed predecessors of: {goal_short}",
            "Reads for prior art and repeated dead ends.",
            "Attacks reinventing known failures without citing them.",
            f"prior art history failed systems related to {goal_short}",
        ),
    }
    roles: list[dict[str, Any]] = []
    for axis in axis_ids:
        name, domain, lens, dissent, deepen = templates[axis]
        roles.append(
            {
                "name": name,
                "domain_description": domain,
                "axis": axis,
                "perspective_lens": lens,
                "dissent_style": dissent,
                "make_description": domain,
                "deepen_query": deepen,
                "existing_expert": None,
            }
        )
    return roles


def _default_consult_prompt(goal: str, roles: list[dict[str, Any]]) -> str:
    role_bits = "; ".join(f"{r.get('name')} ({r.get('axis')})" for r in roles)
    return (
        "Review the following project material (README, roadmap, and related docs) "
        "from your distinct perspective. Discuss in depth: what is missing, what is "
        "overclaimed, what would make this truly exceptional, and what the roadmap "
        "should clarify next. Explicitly surface disagreements between perspectives. "
        "Do not smooth over dissent.\n\n"
        f"Council: {role_bits}\n\n"
        f"Project context:\n{goal.strip()[:12000]}"
    )


def _default_steps(roles: list[dict[str, Any]]) -> list[str]:
    steps = [
        "Review axes_covered and diversity_ok (must PASS before investing deepen spend).",
        "Create missing experts with the make commands (or reuse existing_expert names).",
    ]
    for role in roles:
        steps.append(
            f'Deepen "{role.get("name")}": '
            f'`deepr expert deepen-plan "{role.get("name")}" --query "{role.get("deepen_query")}"` '
            "then Distill no-metered + absorb --trust-class secondary."
        )
    steps += [
        "Regenerate digests and run expert quality on each role (or critical subset).",
        "Consult with explicit -e roster using the challenge consult prompt (--local or --plan).",
        "Edit README/roadmap from agreements and dissent; re-consult after material changes.",
    ]
    return steps


def build_scaffold_council_plan(
    goal: str,
    *,
    role_count: int = _DEFAULT_ROLE_COUNT,
    existing_experts: list[str] | None = None,
) -> ExpertCouncilPlan:
    """Deterministic diverse scaffold (no model)."""
    count = max(_MIN_AXES, min(int(role_count), _MAX_ROLE_COUNT))
    roles = _scaffold_roles(goal, count=count)
    # Optional: mark reuse if name substring matches existing
    existing = existing_experts or []
    for role in roles:
        for name in existing:
            if role["name"].lower() in name.lower() or name.lower() in role["name"].lower():
                role["existing_expert"] = name
                break
    ok, covered = validate_diversity(roles)
    return ExpertCouncilPlan(
        goal=goal.strip(),
        composition_mode="scaffold",
        axes_covered=covered,
        diversity_ok=ok,
        roles=roles,
        consult_prompt=_default_consult_prompt(goal, roles),
        next_operator_steps=_default_steps(roles),
        capacity_notes=[
            "Scaffold mode: no model call. Roles are axis templates specialized lightly to the goal text.",
            "Use --local to compose concrete role names via Ollama when available ($0 API).",
            "Deepen still requires Distill no-metered or other research; council-plan does not research.",
        ],
        limitations=[
            "Scaffold names are templates; replace with project-specific titles after review if needed.",
            "One-shot consult has no multi-turn debate between experts.",
            "cost_usd=0 for plan emission.",
        ],
        cost_usd=0.0,
    )


def _decode_role_list(raw: str) -> list[Any] | None:
    """Decode a model reply into a role list. Form only: no meaning is inferred here."""
    text = raw.strip()
    if not text:
        return None
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
    data: Any
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if isinstance(data, dict):
        data = data.get("roles") or data.get("council") or data.get("experts")
    return data if isinstance(data, list) else None


def _normalize_model_role(item: Any, valid_axes: set[str]) -> dict[str, Any] | None:
    """Coerce one model-proposed role to the plan shape, or drop it."""
    if not isinstance(item, dict):
        return None
    axis = str(item.get("axis") or "").strip()
    if axis not in valid_axes:
        return None
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    domain = str(item.get("domain_description") or item.get("domain") or name).strip()
    return {
        "name": name[:120],
        "domain_description": domain[:500],
        "axis": axis,
        "perspective_lens": str(item.get("perspective_lens") or item.get("lens") or "")[:500],
        "dissent_style": str(item.get("dissent_style") or item.get("dissent") or "")[:500],
        "make_description": str(item.get("make_description") or domain)[:500],
        "deepen_query": str(item.get("deepen_query") or domain)[:300],
        "existing_expert": item.get("existing_expert"),
    }


def _parse_model_roles(raw: str) -> list[dict[str, Any]] | None:
    data = _decode_role_list(raw)
    if data is None:
        return None
    valid_axes = set(_axes_by_id())
    roles = [role for role in (_normalize_model_role(item, valid_axes) for item in data) if role]
    return roles or None


async def compose_council_with_local_model(
    goal: str,
    *,
    role_count: int = _DEFAULT_ROLE_COUNT,
    model: str | None = None,
    existing_experts: list[str] | None = None,
) -> ExpertCouncilPlan:
    """Use local Ollama to propose concrete diverse roles; fall back to scaffold."""
    from deepr.backends.local import default_local_model, ollama_chat_client

    count = max(_MIN_AXES, min(int(role_count), _MAX_ROLE_COUNT))
    axis_spec = [{"id": a["id"], "label": a["label"], "protects": a["protects"]} for a in DIVERSITY_AXES]
    existing = existing_experts or []
    prompt = (
        "Propose a diverse expert council for reviewing a project. "
        "Return ONLY JSON: a list under key roles. Each role object fields: "
        "name, domain_description, axis, perspective_lens, dissent_style, "
        "make_description, deepen_query. "
        f"Use between {count} and {count} roles. "
        f"axis MUST be one of these ids: {[a['id'] for a in DIVERSITY_AXES]}. "
        f"Cover at least {_MIN_AXES} distinct axis ids. "
        "Make roles concrete and non-generic (not five copies of the same domain expert). "
        "Include surprising but relevant outsider lenses when useful.\n\n"
        f"AXIS CATALOG:\n{json.dumps(axis_spec, indent=2)}\n\n"
        f"EXISTING EXPERTS (optional reuse names): {existing}\n\n"
        f"PROJECT / GOAL TEXT:\n{goal[:14000]}"
    )
    try:
        client = ollama_chat_client()
        resolved_model = model or default_local_model()
        response = await client.chat.completions.create(
            model=resolved_model,
            messages=[
                {
                    "role": "system",
                    "content": "You design diverse review councils. Output JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        content = response.choices[0].message.content or ""
        roles = _parse_model_roles(content)
    except Exception:
        roles = None

    if not roles:
        plan = build_scaffold_council_plan(goal, role_count=count, existing_experts=existing)
        plan.composition_mode = "scaffold"
        plan.capacity_notes = [
            "Local model composition failed or returned invalid JSON; scaffold used.",
            *plan.capacity_notes,
        ]
        return plan

    ok, covered = validate_diversity(roles)
    if not ok:
        # Merge with scaffold to satisfy gate
        scaffold = _scaffold_roles(goal, count=count)
        by_axis = {r["axis"]: r for r in roles}
        for s in scaffold:
            by_axis.setdefault(s["axis"], s)
        roles = list(by_axis.values())[:_MAX_ROLE_COUNT]
        ok, covered = validate_diversity(roles)

    for role in roles:
        for name in existing:
            if role["name"].lower() in name.lower() or name.lower() in role["name"].lower():
                role["existing_expert"] = name
                break

    return ExpertCouncilPlan(
        goal=goal.strip(),
        composition_mode="local_model",
        axes_covered=covered,
        diversity_ok=ok,
        roles=roles,
        consult_prompt=_default_consult_prompt(goal, roles),
        next_operator_steps=_default_steps(roles),
        capacity_notes=[
            "Local model composition used ($0 API if Ollama local).",
            "Still run deepen-plan + Distill no-metered before expecting non-generic consult depth.",
            "Claude plan consult synthesis available only when paid-overage-off is proven.",
        ],
        limitations=[
            "Council plan does not create experts or run research by itself.",
            "One-shot consult has no multi-turn debate between experts.",
            "cost_usd=0 for local composition.",
        ],
        cost_usd=0.0,
    )
