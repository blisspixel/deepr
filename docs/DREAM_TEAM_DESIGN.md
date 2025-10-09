# Dream Team Command Design

**Concept:** Show diverse perspectives explicitly, not as abstract "hats" but as actual team members with roles.

## Command Structure

```bash
deepr team analyze "Should we pivot to enterprise vs SMB market?"

# Shows explicit perspectives from:
# - Sarah (Research Lead) - orchestrates, synthesizes
# - Marcus (Data Analyst) - facts, metrics, no interpretation
# - Alex (Strategic Thinker) - opportunities, optimistic
# - Jordan (Risk Analyst) - skeptical, identifies problems
# - Taylor (Creative Strategist) - unconventional angles
```

## Team Roles (Personas, not hats)

### Sarah - Research Lead (Orchestrator)
- Frames the question
- Decides what to research
- Synthesizes team findings
- Makes final recommendation

### Marcus - Data Analyst (Facts)
- Pure facts, no spin
- Market data, metrics, research
- "Here's what the data shows..."
- No opinions, just evidence

### Alex - Strategic Thinker (Optimist)
- Opportunities and upside
- "Here's why this could work..."
- Growth potential
- Market opportunities

### Jordan - Risk Analyst (Skeptic)
- Problems and downside
- "Here's what could go wrong..."
- Challenges and obstacles
- Reality check

### Taylor - Creative Strategist (Unconventional)
- New angles
- "What if we tried..."
- Challenges assumptions
- Novel approaches

## Output Format

```markdown
# Research Question
Should we pivot to enterprise vs SMB market?

## Team Analysis

### Marcus (Data Analyst) - Market Research
[Deep research: market sizes, growth rates, competitive landscape]

Key findings:
- Enterprise market: $X billion, Y% growth
- SMB market: $X billion, Y% growth
- Competitor analysis...

### Alex (Strategic Thinker) - Opportunity Analysis
[Deep research: success stories, growth potential]

Opportunities:
- Enterprise: Higher ACV, predictable revenue
- Competitive moat potential...

### Jordan (Risk Analyst) - Risk Assessment
[Deep research: failure cases, challenges]

Risks:
- Enterprise: Long sales cycles, higher CAC
- SMB: Churn risk, price sensitivity...

### Taylor (Creative Strategist) - Alternative Approaches
[Deep research: novel strategies]

Alternative angles:
- What if we served both with different products?
- What if we started SMB, graduated to enterprise?
- Unconventional go-to-market strategies...

### Sarah (Research Lead) - Synthesis & Recommendation

After reviewing all perspectives:

**Strengths of each approach:**
- Enterprise: [synthesizes Alex + Marcus findings]
- SMB: [synthesizes Alex + Marcus findings]

**Key risks to mitigate:**
- [Addresses Jordan's concerns with data from Marcus]

**Creative options worth exploring:**
- [Evaluates Taylor's alternatives against constraints]

**Recommendation:**
[Balanced synthesis incorporating all perspectives]
```

## Implementation

```python
@prep.command()
@click.argument("question")
@click.option("--topics", default=5, help="Total research tasks across all team members")
def team(question: str, topics: int):
    """
    Multi-perspective research with explicit team roles.

    Each team member researches from their cognitive role:
    - Analyst: Pure facts
    - Strategic Thinker: Opportunities
    - Risk Analyst: Problems
    - Creative: Novel angles
    - Research Lead: Orchestrates and synthesizes

    Makes diverse perspectives visible and shows cognitive conflict.
    """

    # Generate research plan with role assignments
    planner = ResearchPlanner(model="gpt-5")

    plan = planner.plan_team_research(
        question=question,
        max_tasks=topics,
        roles=["analyst", "strategic", "risk", "creative"]
    )

    # Execute with role context
    executor = BatchExecutor()
    results = await executor.execute_with_roles(plan)

    # Synthesize with explicit role attribution
    synthesizer = TeamSynthesizer()
    report = synthesizer.synthesize_perspectives(results)

    print(report)
```

## Why This Works Better Than "Hats"

**Problems with "hats" terminology:**
- Abstract, academic
- Doesn't convey human team dynamic
- "Six Thinking Hats" is dated methodology

**Benefits of team roles:**
- Concrete personas people understand
- "Sarah says..." vs "Blue Hat says..."
- Emphasizes human research team workflow
- More engaging, less jargon

## Philosophy

Research teams work because people with different perspectives challenge each other:
- Optimist finds opportunities Skeptic misses
- Skeptic finds risks Optimist ignores
- Analyst keeps both grounded in facts
- Creative suggests angles neither considered
- Lead synthesizes into balanced view

**Conflict is a feature, not a bug.** When team members disagree, that creates better analysis.

Deepr automates this dynamic but makes it visible so users understand WHY recommendations are balanced.
