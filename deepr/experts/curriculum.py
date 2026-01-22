"""Self-directed learning curriculum generation for domain experts.

This module enables experts to autonomously generate comprehensive learning plans
based on their domain and initial knowledge base.
"""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import json
from openai import AsyncOpenAI

from deepr.config import AppConfig


@dataclass
class LearningTopic:
    """A single topic in the learning curriculum."""

    title: str
    description: str
    research_mode: str  # "campaign" for deep research, "focus" for quick lookup
    research_type: str  # "academic", "documentation", "best-practices", "trends", "technical-deep-dive"
    estimated_cost: float
    estimated_minutes: int
    priority: int  # 1 (highest) to 5 (lowest)
    research_prompt: str
    dependencies: List[str] = None  # Topic titles this depends on

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


@dataclass
class LearningCurriculum:
    """Complete learning curriculum for an expert."""

    expert_name: str
    domain: str
    topics: List[LearningTopic]
    total_estimated_cost: float
    total_estimated_minutes: int
    generated_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "expert_name": self.expert_name,
            "domain": self.domain,
            "topics": [
                {
                    "title": t.title,
                    "description": t.description,
                    "research_mode": t.research_mode,
                    "research_type": t.research_type,
                    "estimated_cost": t.estimated_cost,
                    "estimated_minutes": t.estimated_minutes,
                    "priority": t.priority,
                    "research_prompt": t.research_prompt,
                    "dependencies": t.dependencies
                }
                for t in self.topics
            ],
            "total_estimated_cost": self.total_estimated_cost,
            "total_estimated_minutes": self.total_estimated_minutes,
            "generated_at": self.generated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LearningCurriculum':
        """Create from dictionary."""
        return cls(
            expert_name=data["expert_name"],
            domain=data["domain"],
            topics=[
                LearningTopic(
                    title=t["title"],
                    description=t["description"],
                    research_mode=t.get("research_mode", "focus"),  # Default to focus if not specified
                    research_type=t.get("research_type", "best-practices"),  # Default type
                    estimated_cost=t["estimated_cost"],
                    estimated_minutes=t["estimated_minutes"],
                    priority=t["priority"],
                    research_prompt=t["research_prompt"],
                    dependencies=t.get("dependencies", [])
                )
                for t in data["topics"]
            ],
            total_estimated_cost=data["total_estimated_cost"],
            total_estimated_minutes=data["total_estimated_minutes"],
            generated_at=datetime.fromisoformat(data["generated_at"])
        )


class CurriculumGenerator:
    """Generates comprehensive learning curricula for domain experts."""

    def __init__(self, config: AppConfig):
        self.config = config

    async def generate_curriculum(
        self,
        expert_name: str,
        domain: str,
        initial_documents: List[str],
        target_topics: int = 15,
        budget_limit: Optional[float] = None
    ) -> LearningCurriculum:
        """Generate a learning curriculum for an expert.

        Args:
            expert_name: Name of the expert
            domain: Domain description
            initial_documents: List of initial document filenames/paths
            target_topics: Target number of topics (10-20)
            budget_limit: Optional budget constraint

        Returns:
            LearningCurriculum with topics ordered by priority and dependencies
        """
        # Build the curriculum generation prompt
        prompt = self._build_curriculum_prompt(
            expert_name, domain, initial_documents, target_topics, budget_limit
        )

        # Use GPT-5 for curriculum planning (best for structured reasoning and planning)
        if isinstance(self.config, dict):
            api_key = self.config.get("api_key") or self.config.get("openai_api_key")
        else:
            # AppConfig object
            api_key = self.config.provider.openai_api_key
        client = AsyncOpenAI(api_key=api_key)

        # GPT-5 uses Responses API for improved agentic performance
        response_obj = await client.responses.create(
            model="gpt-5",  # GPT-5: best for agentic planning and structured output
            input=[
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "You are an expert curriculum designer."}]
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}]
                }
            ]
        )

        # Extract the response content from Responses API format
        response = ""
        for output_item in response_obj.output:
            if output_item.type == "message":
                for content_item in output_item.content:
                    if content_item.type == "output_text":
                        response += content_item.text

        # Parse the structured response
        curriculum = self._parse_curriculum_response(
            response, expert_name, domain
        )

        # Validate budget constraints
        if budget_limit and curriculum.total_estimated_cost > budget_limit:
            # Truncate to fit budget
            curriculum = self._truncate_to_budget(curriculum, budget_limit)

        return curriculum

    def _build_curriculum_prompt(
        self,
        expert_name: str,
        domain: str,
        initial_documents: List[str],
        target_topics: int,
        budget_limit: Optional[float]
    ) -> str:
        """Build the curriculum generation prompt."""

        today = datetime.utcnow().strftime("%Y-%m-%d")

        doc_list = "\n".join(f"- {doc}" for doc in initial_documents)

        budget_guidance = ""
        if budget_limit:
            # Calculate how many deep research topics we can afford
            deep_topics = min(5, target_topics)  # Always aim for 5 deep topics
            quick_topics = target_topics - deep_topics

            budget_guidance = f"""
BUDGET CONSTRAINT: ${budget_limit:.2f}
TARGET TOPICS: {target_topics} (recommend 15-20 for true expertise, not just 10)

AVAILABLE MODELS - Match the right tool to each task type:

1. **CAMPAIGN** (o4-mini-deep-research): $1.50-2.50, 10-45 min
   - Extended reasoning + web browsing
   - Use for: WHY questions, trade-off analysis, architectural reasoning
   - Best for: Foundational principles, decision frameworks

2. **FOCUS** (gpt-5.2 with reasoning.effort=medium): $0.20-0.30, 1-5 min
   - Web search + structured thinking
   - Use for: Current state, documentation synthesis, evolution analysis
   - Best for: What exists NOW, how we got here, trends

SMART ALLOCATION (optimize for budget efficiency):

**CURRENT STATE** (~30% = {int(target_topics * 0.30)} topics) - FOCUS
- What's new (last 6 months): FOCUS ($0.30)
- Major product deep dives (2-4): FOCUS ($0.25 each)
- Feature/version comparisons (1-2): FOCUS ($0.20 each)
Subtotal: ~$1.50

**FOUNDATIONAL DEPTH** (~25% = {int(target_topics * 0.25)} topics) - CAMPAIGN
- Core architectural patterns: CAMPAIGN ($2.00)
- Security/compliance fundamentals: CAMPAIGN ($2.00)
- Design principles that transcend tech: CAMPAIGN ($2.00)
- 3-4 deep topics requiring extended reasoning
Subtotal: ~${int(target_topics * 0.25) * 2.00:.2f}

**HISTORICAL CONTEXT** (~15% = {int(target_topics * 0.15)} topics) - FOCUS
- Domain evolution (how we got here): FOCUS ($0.25)
- Lessons from past failures: FOCUS ($0.25)
Subtotal: ~${int(target_topics * 0.15) * 0.25:.2f}

**COMPARATIVE WISDOM** (~20% = {int(target_topics * 0.20)} topics) - MIXED
- Decision framework (when to use X vs Y): CAMPAIGN ($2.00)
- Specific tool comparisons (2-3): FOCUS ($0.20 each)
- Common pitfalls: FOCUS ($0.25)
Subtotal: ~$2.60

**FUTURE VISION** (~10% = {int(target_topics * 0.10)} topics) - FOCUS
- Emerging trends 2026-2027: FOCUS ($0.25)
- Industry direction signals: FOCUS ($0.25)
Subtotal: ~${int(target_topics * 0.10) * 0.25:.2f}

TOTAL ESTIMATED: ${(int(target_topics * 0.25) * 2.00) + 2.00 + (int(target_topics * 0.75) * 0.25):.2f}
FITS IN BUDGET: {"YES" if ((int(target_topics * 0.25) * 2.00) + 2.00 + (int(target_topics * 0.75) * 0.25)) <= budget_limit else "NO - reduce CAMPAIGN topics"}

KEY INSIGHT: Use 15-20 topics, not just 10. Most are cheap FOCUS ($0.20-0.30),
only 3-5 expensive CAMPAIGN ($2.00) for deep reasoning. More topics = better expert.
"""

        return f"""You are designing a self-directed learning curriculum for a domain expert.

EXPERT PROFILE:
- Name: {expert_name}
- Domain: {domain}
- Initial Knowledge Base:
{doc_list}

OBJECTIVE:
Generate a comprehensive learning curriculum of {target_topics} research topics that will transform this expert from having basic document knowledge to deep domain expertise.

TODAY'S DATE: {today}

CRITICAL - BUILD A TRUE EXPERT (Not Just Documentation Reader!):

A real expert has FIVE dimensions of knowledge. You MUST cover all five:

**DIMENSION 1: CURRENT STATE (30% of topics)**
Purpose: What exists RIGHT NOW in {today.split('-')[0]}
- Topic #1 MANDATORY: "What's new in [domain] last 6 months?" (CAMPAIGN, trends, priority 1)
  Must list ALL new products/services with launch dates and conference announcements
  Example: "Comprehensive survey Microsoft AI Oct 2025-{today}: Agent 365 (Ignite 2025), Copilot updates, Azure AI Foundry. List each with launch date."
- Topics #2-3: Deep dives on 2 major new products from Topic #1 (CAMPAIGN or FOCUS)
- Current best practices, latest features, what's GA vs preview

**DIMENSION 2: FOUNDATIONAL DEPTH (25% of topics)**
Purpose: Timeless principles that don't age
- Core architectural patterns (microservices, event-driven, etc.)
- Theoretical foundations (CAP theorem, consistency models, security fundamentals)
- Why things work the way they do (not just HOW, but WHY)
- Design patterns that have stood the test of time
- Use "academic" or "technical-deep-dive" research types

**DIMENSION 3: HISTORICAL CONTEXT (15% of topics)**
Purpose: Learn from the past to understand the present
- Evolution of the domain (where we came from)
- What problems led to current solutions (why GraphQL after REST, why K8s after Docker Swarm)
- Failed approaches and why they failed (lessons learned)
- How the industry got to where it is today
- This prevents repeating past mistakes

**DIMENSION 4: COMPARATIVE WISDOM (20% of topics)**
Purpose: Make good decisions through trade-off analysis
- When to use X vs Y (with real criteria)
- Cost-performance-complexity trade-offs
- Real-world case studies (successes AND failures)
- Common pitfalls and anti-patterns
- "Here's what docs say, here's what really happens"
- Battle-tested implementation patterns

**DIMENSION 5: FUTURE VISION (10% of topics)**
Purpose: Prepare for what's coming
- Emerging trends and patterns (2026-2027)
- Industry direction and momentum
- What's in early adopter phase
- Where the ecosystem is heading

WHY THIS STRUCTURE:
An expert who only knows latest docs is shallow and unhelpful. They need:
- Current state: So they know what exists NOW (Agent 365, latest features)
- Foundational depth: So they understand WHY (not just copy-paste docs)
- Historical context: So they learn from past failures
- Comparative wisdom: So they make good trade-off decisions
- Future vision: So they prepare for what's next

CURRICULUM REQUIREMENTS:

1. **Topics 1-3 (30%): CURRENT STATE**
   - #1: What's new (MANDATORY FIRST TOPIC)
   - #2-3: Deep dives on major recent products

2. **Topics 4-5 (25%): FOUNDATIONAL DEPTH**
   - Timeless principles, architecture patterns, theory
   - Use "academic" or "technical-deep-dive" types

3. **Topic 6 (15%): HISTORICAL CONTEXT**
   - Evolution of domain, lessons learned, why we're here

4. **Topics 7-8 (20%): COMPARATIVE WISDOM**
   - Trade-offs, when to use what, case studies, pitfalls

5. **Topic 9-10 (10%): FUTURE VISION**
   - Emerging trends, 2026-2027 direction

THINK HOLISTICALLY:
- An expert needs to understand systems from multiple angles
- Different contexts require different knowledge (e.g., Python vs Node.js patterns)
- Security, cost, and compliance cut across all layers
- Real-world solutions combine multiple services/patterns

{budget_guidance}

TOPIC STRUCTURE:
For each topic, provide:
- title: Clear, specific topic name
- description: 1-2 sentences explaining what will be learned
- research_mode: "campaign" for deep research topics (5 max), "focus" for quick lookups (rest)
- research_type: One of:
  * "academic" - Research papers, theoretical foundations
  * "technical-deep-dive" - Architectural patterns, algorithms
  * "trends" - Market analysis, future directions
  * "documentation" - Latest APIs, SDKs, tools, services
  * "best-practices" - Real-world implementation patterns
- estimated_cost: $1.50-2.50 for campaign, $0.15-0.30 for focus
- estimated_minutes: 30-60 for campaign, 8-15 for focus
- priority: 1 (critical foundation) to 5 (nice-to-have)
- research_prompt: The exact prompt to use for research
  * CRITICAL: Must be under 300 characters (hard limit for API)
  * Be concise but specific
  * Include year {today.split('-')[0]} for currency
  * Example: "Survey 2025 temporal knowledge graph models (DyRep, TNTComplEx) for agent memory and hybrid vector+graph storage architectures"
- dependencies: List of topic titles that should be researched first

OUTPUT FORMAT (JSON):
{{
  "topics": [
    {{
      "title": "Topic name",
      "description": "What will be learned",
      "research_mode": "campaign",
      "research_type": "academic",
      "estimated_cost": 2.00,
      "estimated_minutes": 45,
      "priority": 1,
      "research_prompt": "Research prompt with year {today.split('-')[0]}",
      "dependencies": []
    }}
  ]
}}

IMPORTANT GUIDELINES:
- **EXACTLY 5 topics must use "campaign" mode** with mix of research types:
  * 2-3 should be "academic" or "technical-deep-dive" (timeless foundations)
  * 0-1 should be "trends" (future analysis)
- Remaining topics use "focus" mode with mix of:
  * 3-5 should be "documentation" (latest tools, APIs, services)
  * 2-4 should be "best-practices" (real-world patterns)
- Each research prompt should be specific and actionable
- For "documentation" type: Include specific service/tool names and year {today.split('-')[0]}
- For "academic" type: Request research papers, citations, and theoretical foundations
- For "best-practices" type: Request case studies, patterns, and proven approaches
- Estimated costs:
  - Campaign: $1.50-2.50 (multi-phase deep research)
  - Focus: $0.15-0.30 (single-phase targeted lookup)
- Total topics: exactly {target_topics}
- Priority 1-2 for campaign topics (foundations)
- Priority 3-5 for focus topics (supplementary)
- Dependencies create logical learning flow

EXAMPLE - Microsoft AI Expert (10 topics, TRUE EXPERT):

**CURRENT STATE (Topics 1-3):**
#1: "What's new in Microsoft AI (Oct 2025 - {today})?" (CAMPAIGN, trends, priority 1)
    "Comprehensive survey Microsoft AI Oct 2025-{today}: Agent 365 (Ignite 2025), Copilot updates, Azure AI Foundry, new models. List each with launch date and status."

#2: "Agent 365 deep dive: architecture and use cases" (CAMPAIGN, documentation, priority 1)
    "Complete guide to Agent 365 (Ignite 2025): architecture, orchestration, tool calling, integration with M365 Copilot, preview status, pricing."

#3: "Azure AI Foundry vs AI Studio: 2026 comparison" (FOCUS, best-practices, priority 2)
    "Compare Azure AI Foundry and AI Studio in 2026: features, use cases, migration path, when to use which, pricing differences."

**FOUNDATIONAL DEPTH (Topics 4-5):**
#4: "RAG architecture patterns: naive to agentic" (CAMPAIGN, technical-deep-dive, priority 1)
    "Compare RAG approaches: naive retrieval, hybrid search, re-ranking, agentic retrieval. Trade-offs, when to use each, implementation patterns."

#5: "LLM security fundamentals: injection to data leakage" (CAMPAIGN, academic, priority 2)
    "LLM security threats: prompt injection, data leakage, model theft, jailbreaking. Mitigations, defense patterns, Purview integration."

**HISTORICAL CONTEXT (Topic 6):**
#6: "Evolution of Microsoft AI: LUIS to GPT-5" (FOCUS, trends, priority 3)
    "Microsoft AI evolution 2018-2026: LUIS, Bot Framework, Cognitive Services, OpenAI partnership, Copilot, Agent 365. Why each shift happened."

**COMPARATIVE WISDOM (Topics 7-8):**
#7: "OpenAI vs Azure OpenAI vs M365 Copilot: decision framework" (FOCUS, best-practices, priority 2)
    "When to use OpenAI API vs Azure OpenAI vs M365 Copilot: cost, governance, features, integration. Real-world case studies."

#8: "Common AI implementation pitfalls in enterprise" (FOCUS, best-practices, priority 3)
    "Top failures in enterprise AI: context window misuse, cost overruns, poor prompt design, security gaps. How to avoid each."

**FUTURE VISION (Topics 9-10):**
#9: "Agentic AI trends: 2026-2027 direction" (FOCUS, trends, priority 3)
    "Emerging patterns in agentic AI: multi-agent systems, tool orchestration, autonomous planning. What's coming in next 12 months."

#10: "Microsoft AI roadmap signals: Ignite 2025 analysis" (FOCUS, trends, priority 4)
    "Read between the lines of Ignite 2025: what Microsoft is betting on, deprecation signals, strategic direction."

This creates an expert who:
- Knows Agent 365 and latest products (Current State)
- Understands WHY RAG patterns exist (Foundational Depth)
- Knows how we got from LUIS to today (Historical Context)
- Can make OpenAI vs Azure decisions (Comparative Wisdom)
- Anticipates what's coming next (Future Vision)

Generate the curriculum now:"""

    def _parse_curriculum_response(
        self,
        response: str,
        expert_name: str,
        domain: str
    ) -> LearningCurriculum:
        """Parse the GPT response into a LearningCurriculum."""

        # Extract JSON from response (handle markdown code blocks)
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse curriculum JSON: {e}\n{json_str}")

        # Create LearningTopic objects
        topics = []
        for topic_data in data["topics"]:
            topics.append(LearningTopic(
                title=topic_data["title"],
                description=topic_data["description"],
                research_mode=topic_data.get("research_mode", "focus"),
                research_type=topic_data.get("research_type", "best-practices"),
                estimated_cost=topic_data["estimated_cost"],
                estimated_minutes=topic_data["estimated_minutes"],
                priority=topic_data["priority"],
                research_prompt=topic_data["research_prompt"],
                dependencies=topic_data.get("dependencies", [])
            ))

        # Calculate totals
        total_cost = sum(t.estimated_cost for t in topics)
        total_minutes = sum(t.estimated_minutes for t in topics)

        return LearningCurriculum(
            expert_name=expert_name,
            domain=domain,
            topics=topics,
            total_estimated_cost=total_cost,
            total_estimated_minutes=total_minutes,
            generated_at=datetime.utcnow()
        )

    def _truncate_to_budget(
        self,
        curriculum: LearningCurriculum,
        budget_limit: float
    ) -> LearningCurriculum:
        """Truncate curriculum to fit within budget while preserving priorities."""

        # Sort by priority (1 = highest), then by cost
        sorted_topics = sorted(
            curriculum.topics,
            key=lambda t: (t.priority, t.estimated_cost)
        )

        # Keep adding topics until we hit budget
        selected_topics = []
        running_cost = 0.0

        for topic in sorted_topics:
            if running_cost + topic.estimated_cost <= budget_limit:
                selected_topics.append(topic)
                running_cost += topic.estimated_cost
            else:
                # Check if we can fit any remaining priority 1-2 topics
                if topic.priority <= 2 and running_cost + topic.estimated_cost <= budget_limit * 1.1:
                    # Allow 10% overage for critical topics
                    selected_topics.append(topic)
                    running_cost += topic.estimated_cost

        # Recalculate totals
        total_cost = sum(t.estimated_cost for t in selected_topics)
        total_minutes = sum(t.estimated_minutes for t in selected_topics)

        return LearningCurriculum(
            expert_name=curriculum.expert_name,
            domain=curriculum.domain,
            topics=selected_topics,
            total_estimated_cost=total_cost,
            total_estimated_minutes=total_minutes,
            generated_at=curriculum.generated_at
        )

    def get_execution_order(self, curriculum: LearningCurriculum) -> List[List[LearningTopic]]:
        """Get topics organized into execution phases based on dependencies.

        Returns:
            List of phases, where each phase is a list of topics that can be
            researched in parallel (no dependencies on each other).
        """
        phases = []
        completed = set()
        remaining = list(curriculum.topics)

        while remaining:
            # Find topics with no unmet dependencies
            ready = []
            for topic in remaining:
                deps_met = all(dep in completed for dep in topic.dependencies)
                if deps_met:
                    ready.append(topic)

            if not ready:
                # Circular dependency or error - just take everything remaining
                phases.append(remaining)
                break

            # This phase can run in parallel
            phases.append(ready)

            # Mark as completed
            for topic in ready:
                completed.add(topic.title)
                remaining.remove(topic)

        return phases
