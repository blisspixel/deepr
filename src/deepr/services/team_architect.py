"""
Team Architect - Dynamically assemble optimal research teams.

Uses GPT-5 to determine what perspectives a question needs, then assembles
diverse team with relevant expertise.

No static personas. Each question gets a custom dream team.
"""

import json
import logging
import os
from typing import Any

from openai import OpenAI

from deepr.utils.prompt_security import sanitize_untrusted_content

logger = logging.getLogger(__name__)


class TeamArchitect:
    """
    Assembles optimal research teams for specific questions.

    Uses GPT-5 to reason about:
    - What expertise this question needs
    - What perspectives create best analysis
    - What cognitive diversity prevents blind spots
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-5"):
        """
        Initialize team architect.

        Args:
            api_key: OpenAI API key
            model: GPT-5 model for team design
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = OpenAI(api_key=self.api_key, max_retries=0)
        self.model = model

    def design_team(
        self,
        question: str,
        context: str | None = None,
        team_size: int = 5,
        research_company: str | None = None,
        perspective_lens: str | None = None,
        adversarial: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Design optimal research team for this question.

        Args:
            question: Research question
            context: Additional context
            team_size: Number of team members
            research_company: Company name to research for grounded personas
            perspective_lens: Cultural/demographic perspective (e.g., "Japanese business culture", "Gen Z")
            adversarial: Weight team toward skeptical/devil's advocate perspectives

        Returns:
            List of team members with roles, focus, perspective

        Example:
            [
                {
                    "role": "Enterprise SaaS Market Analyst",
                    "focus": "Enterprise vs SMB market dynamics and trends",
                    "perspective": "data-driven",
                    "rationale": "Need objective market data to ground decision"
                },
                {
                    "role": "Former Enterprise Buyer",
                    "focus": "Enterprise buying process and decision criteria",
                    "perspective": "customer",
                    "rationale": "Customer perspective prevents product-centric thinking"
                },
                ...
            ]
        """
        # If company specified, first research actual people
        company_intel = None
        if research_company:
            company_intel = self._research_company_people(research_company)

        prompt = self._build_team_design_prompt(
            question, context, team_size, company_intel, perspective_lens, adversarial
        )

        from deepr.services.metered_call import execute_reserved_sync_call

        response = execute_reserved_sync_call(
            operation_prefix="team-design",
            provider="openai",
            model=self.model,
            source="services.team_architect.design_team",
            call=lambda: self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a research team architect. Design optimal teams with diverse perspectives.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            ),
        )

        result = json.loads(response.choices[0].message.content or "{}")
        return result.get("team", [])

    def _research_company_people(self, company: str) -> dict[str, Any] | None:
        """
        Research actual executives/board members for grounded personas.

        Args:
            company: Company name

        Returns:
            Dict with executives, board members, and backgrounds
        """
        prompt = f"""Research {company}'s current leadership team.

Find:
1. CEO and C-suite executives (names, backgrounds, previous roles)
2. Board members (names, backgrounds, notable experience)
3. Key advisors or notable investors if public

Focus on:
- Current roles and previous companies
- Areas of expertise
- Notable achievements or specializations
- Educational background if relevant

Return JSON:
{{
  "executives": [
    {{
      "name": "Full Name",
      "role": "Current role",
      "background": "Brief summary of previous experience",
      "expertise": ["area1", "area2"]
    }}
  ],
  "board": [
    {{
      "name": "Full Name",
      "role": "Board position",
      "background": "Brief summary",
      "expertise": ["area1", "area2"]
    }}
  ],
  "summary": "Brief overview of leadership's collective background"
}}

Only include people you find with actual research. If unable to find information, return empty lists."""

        try:
            from deepr.services.metered_call import execute_reserved_sync_call

            response = execute_reserved_sync_call(
                operation_prefix="company-leadership",
                provider="openai",
                model="gpt-5",
                source="services.team_architect.research_company_people",
                call=lambda: self.client.chat.completions.create(
                    model="gpt-5",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a research analyst. Find factual information about company leadership.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                ),
            )

            return json.loads(response.choices[0].message.content or "{}")
        except Exception as e:
            logger.warning("Could not research company people: %s", e)
            return None

    def _build_team_design_prompt(
        self,
        question: str,
        context: str | None,
        team_size: int,
        company_intel: dict[str, Any] | None = None,
        perspective_lens: str | None = None,
        adversarial: bool = False,
    ) -> str:
        """Build prompt for GPT-5 to design team."""

        parts = ["# Research Question", f"\n{question}\n"]

        if context:
            parts.append(f"\n## Context\n{context}\n")

        if perspective_lens:
            parts.append("\n## Perspective Lens\n")
            parts.append(
                f"**IMPORTANT:** All team members must analyze this question through the lens of: **{perspective_lens}**\n\n"
            )
            parts.append("This means:\n")
            parts.append("- Team members should represent or understand this perspective deeply\n")
            parts.append("- Research focus should consider cultural context, values, and priorities of this group\n")
            parts.append(f"- Analysis should reflect how {perspective_lens} would approach this question\n\n")

        if company_intel:
            parts.append("\n## Company Leadership Intelligence\n")
            parts.append("Use this source data to ground personas in real people:\n\n")
            intelligence_block = sanitize_untrusted_content(
                _render_company_intelligence(company_intel),
                source_label="company leadership intelligence",
            )
            parts.append(f"{intelligence_block.delimited}\n\n")

            parts.append(
                "**IMPORTANT:** Create personas grounded in these actual people's backgrounds and expertise. Don't use their exact names, but use their real experience to inform persona design.\n\n"
            )

        if adversarial:
            parts.append("\n## ADVERSARIAL MODE\n")
            parts.append("Weight the team HEAVILY toward skeptical, critical, and devil's advocate perspectives.\n")
            parts.append("Goal: Find flaws, challenge assumptions, identify risks before reality does.\n")
            parts.append("Majority of team should be focused on what could go wrong, not what could go right.\n\n")

        parts.append(f"""
## Your Task

Design the optimal {team_size}-person research team for THIS specific question.

**Requirements:**

1. **Diverse perspectives**{" - WEIGHTED TOWARD SKEPTICAL in adversarial mode" if adversarial else " - Not all optimistic, not all skeptical"}
   - Include data-driven perspectives (objective facts)
   {"" if adversarial else "- Include optimistic perspectives (opportunities, upside)"}
   - Include skeptical perspectives (risks, problems, reality check){" - MAJORITY" if adversarial else ""}
   - Include customer/user perspectives (real-world experience)
   {"" if adversarial else "- Include creative perspectives (unconventional angles)"}
   {"- Include adversarial perspectives (challenge core assumptions, find fatal flaws)" if adversarial else ""}

2. **Relevant expertise** - Specific to this question, not generic
   - Bad: "Data Analyst" (too generic)
   - Good: "Enterprise SaaS Market Analyst" (specific expertise)
   - Bad: "Researcher" (meaningless)
   - Good: "Former Enterprise Buyer at Fortune 500" (real expertise)

3. **Cognitive diversity** - Different ways of thinking
   - Some quantitative (numbers, data, metrics)
   - Some qualitative (stories, experience, intuition)
   - Some strategic (big picture)
   - Some tactical (execution details)

4. **Conflict is good** - Design for productive disagreement
   - Optimist will find opportunities Skeptic misses
   - Skeptic will find risks Optimist ignores
   - This creates better analysis

**Output Format:**

Return JSON:
```json
{{
  "team": [
    {{
      "role": "Specific role with expertise (e.g., 'Enterprise SaaS Market Analyst')",
      "focus": "What they'll research (e.g., 'Enterprise vs SMB market dynamics, growth rates, competitive landscape')",
      "perspective": "Cognitive angle (data-driven, optimistic, skeptical, customer-focused, creative, strategic, tactical, quantitative, qualitative)",
      "rationale": "Why this role is valuable for THIS question (1 sentence)"
    }},
    ...
  ],
  "team_rationale": "Why THIS team composition creates best analysis for THIS question (2-3 sentences)"
}}
```

**Examples of good role design:**

Question: "Should we pivot to enterprise?"
- "Enterprise SaaS Market Analyst" (data on enterprise trends)
- "Former Enterprise Buyer at Fortune 500" (customer perspective)
- "Series A VC focusing on B2B SaaS" (market dynamics)
- "Product Strategist who built enterprise features" (product implications)
- "CFO who scaled SMB to enterprise" (financial reality check)

Question: "How do we compete with Notion?"
- "Product Analyst specializing in productivity tools" (feature comparison)
- "Go-to-Market Strategist with PLG experience" (distribution analysis)
- "Former Notion power user who churned" (customer perspective)
- "Developer Relations expert" (community dynamics)
- "Pricing strategist for SaaS" (monetization analysis)

Now design the optimal team for the question above.
""")

        return "".join(parts)


class TeamSynthesizer:
    """
    Synthesizes team research with attribution and conflict analysis.

    Shows where perspectives agree, where they conflict, weighs evidence.
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-5"):
        """Initialize synthesizer."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = OpenAI(api_key=self.api_key, max_retries=0)
        self.model = model

    def synthesize_with_conflict_analysis(self, question: str, team_results: list[dict[str, Any]]) -> str:
        """
        Synthesize team findings with attribution.

        Args:
            question: Original question
            team_results: List of results with team_member info and research

        Returns:
            Markdown report with synthesis
        """
        prompt = self._build_synthesis_prompt(question, team_results)

        from deepr.services.metered_call import execute_reserved_sync_call

        response = execute_reserved_sync_call(
            operation_prefix="team-synthesis",
            provider="openai",
            model=self.model,
            source="services.team_architect.synthesize_with_conflict_analysis",
            call=lambda: self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are the Lead Researcher synthesizing diverse team perspectives. Show your work. Make conflicts explicit. Attribute findings to team members.",
                    },
                    {"role": "user", "content": prompt},
                ],
            ),
        )

        return response.choices[0].message.content or ""

    def _build_synthesis_prompt(self, question: str, team_results: list[dict[str, Any]]) -> str:
        """Build synthesis prompt."""

        parts = ["# Research Question", f"\n{question}\n", "\n## Team Findings\n"]

        for index, result in enumerate(team_results, 1):
            member = result.get("team_member", {})
            role = sanitize_untrusted_content(
                member.get("role", "Unknown"), source_label=f"team role {index}"
            ).sanitized
            perspective = sanitize_untrusted_content(
                member.get("perspective", ""), source_label=f"team perspective {index}"
            ).sanitized
            focus = sanitize_untrusted_content(member.get("focus", ""), source_label=f"team focus {index}").sanitized
            findings = result.get("result", "")
            findings_block = sanitize_untrusted_content(findings, source_label=f"team finding {index}")

            parts.append(f"\n### {role}")
            parts.append(f"\n**Perspective:** {perspective}")
            parts.append(f"\n**Focus:** {focus}\n")
            parts.append(f"\n{findings_block.delimited}\n")
            parts.append("\n---\n")

        parts.append("""
## Your Task

Synthesize these diverse perspectives into a balanced analysis.

**Requirements:**

1. **Maintain attribution** - Credit team members for insights
   - "According to [Enterprise Market Analyst], the enterprise market..."
   - "The [Former Enterprise Buyer] noted that..."

2. **Highlight agreements** - Where perspectives converge
   - "Both [Analyst] and [Strategist] found that..."
   - "Across all perspectives, the data shows..."

3. **Show conflicts explicitly** - Where perspectives disagree
   - "[Optimist] sees opportunity in X, but [Skeptic] warns that..."
   - "While [Market Analyst] reports Y% growth, [Customer] experienced..."
   - **Conflicts are valuable** - they reveal nuance

4. **Weigh evidence** - Not all perspectives equal
   - Data-driven findings > speculation
   - Customer experience > assumptions
   - Multiple confirming sources > single source

5. **Synthesize, don't summarize** - Create new insights
   - Connect findings across perspectives
   - Identify patterns team members didn't see individually
   - Resolve conflicts with additional reasoning

6. **Make recommendation** - Balanced, evidence-based
   - Supported by team findings
   - Acknowledges risks (from skeptics)
   - Identifies opportunities (from optimists)
   - Grounded in data (from analysts)

**Output Format:**

```markdown
# Team Analysis: [Question]

## Key Findings

### Areas of Agreement
[Where multiple team members converged on same conclusions]

### Points of Conflict
[Where perspectives disagreed - explain both sides]

## Synthesis by Theme

### [Theme 1]
[Synthesize findings across team members]

According to [Role], [finding]. This aligns with [Other Role]'s observation that [finding].

However, [Skeptical Role] cautions that [concern].

[Your synthesis connecting these perspectives]

### [Theme 2]
...

## Recommendation

Based on the team's diverse perspectives:

**Strengths:** [Supported by which team members]

**Risks:** [Identified by which team members]

**Recommendation:** [Balanced conclusion]

**Rationale:** [Why this balances the evidence from all perspectives]
```
""")

        return "".join(parts)


def _render_company_intelligence(company_intel: dict[str, Any]) -> str:
    """Render company intelligence for a bounded prompt source block."""
    lines: list[str] = []

    if company_intel.get("executives"):
        lines.append("Executives:")
        for executive in company_intel["executives"]:
            name = executive.get("name", "Unknown")
            role = executive.get("role", "Unknown role")
            background = executive.get("background", "")
            lines.append(f"- {name} ({role}): {background}")
        lines.append("")

    if company_intel.get("board"):
        lines.append("Board:")
        for board_member in company_intel["board"]:
            name = board_member.get("name", "Unknown")
            role = board_member.get("role", "Unknown role")
            background = board_member.get("background", "")
            lines.append(f"- {name} ({role}): {background}")
        lines.append("")

    if company_intel.get("summary"):
        lines.append(f"Summary: {company_intel['summary']}")

    return "\n".join(lines)
