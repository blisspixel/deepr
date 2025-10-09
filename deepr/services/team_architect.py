"""
Team Architect - Dynamically assemble optimal research teams.

Uses GPT-5 to determine what perspectives a question needs, then assembles
diverse team with relevant expertise.

No static personas. Each question gets a custom dream team.
"""

import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI


class TeamArchitect:
    """
    Assembles optimal research teams for specific questions.

    Uses GPT-5 to reason about:
    - What expertise this question needs
    - What perspectives create best analysis
    - What cognitive diversity prevents blind spots
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5"):
        """
        Initialize team architect.

        Args:
            api_key: OpenAI API key
            model: GPT-5 model for team design
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def design_team(
        self,
        question: str,
        context: Optional[str] = None,
        team_size: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Design optimal research team for this question.

        Args:
            question: Research question
            context: Additional context
            team_size: Number of team members

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
        prompt = self._build_team_design_prompt(question, context, team_size)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a research team architect. Design optimal teams with diverse perspectives."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return result.get("team", [])

    def _build_team_design_prompt(
        self,
        question: str,
        context: Optional[str],
        team_size: int
    ) -> str:
        """Build prompt for GPT-5 to design team."""

        parts = [
            "# Research Question",
            f"\n{question}\n"
        ]

        if context:
            parts.append(f"\n## Context\n{context}\n")

        parts.append(f"""
## Your Task

Design the optimal {team_size}-person research team for THIS specific question.

**Requirements:**

1. **Diverse perspectives** - Not all optimistic, not all skeptical
   - Include data-driven perspectives (objective facts)
   - Include optimistic perspectives (opportunities, upside)
   - Include skeptical perspectives (risks, problems, reality check)
   - Include customer/user perspectives (real-world experience)
   - Include creative perspectives (unconventional angles)

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

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5"):
        """Initialize synthesizer."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def synthesize_with_conflict_analysis(
        self,
        question: str,
        team_results: List[Dict[str, Any]]
    ) -> str:
        """
        Synthesize team findings with attribution.

        Args:
            question: Original question
            team_results: List of results with team_member info and research

        Returns:
            Markdown report with synthesis
        """
        prompt = self._build_synthesis_prompt(question, team_results)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are the Lead Researcher synthesizing diverse team perspectives. Show your work. Make conflicts explicit. Attribute findings to team members."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content

    def _build_synthesis_prompt(
        self,
        question: str,
        team_results: List[Dict[str, Any]]
    ) -> str:
        """Build synthesis prompt."""

        parts = [
            "# Research Question",
            f"\n{question}\n",
            "\n## Team Findings\n"
        ]

        for result in team_results:
            member = result.get("team_member", {})
            role = member.get("role", "Unknown")
            perspective = member.get("perspective", "")
            focus = member.get("focus", "")
            findings = result.get("result", "")

            parts.append(f"\n### {role}")
            parts.append(f"\n**Perspective:** {perspective}")
            parts.append(f"\n**Focus:** {focus}\n")
            parts.append(f"\n{findings}\n")
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
