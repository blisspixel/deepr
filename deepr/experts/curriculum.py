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
        api_key = self.config.get("api_key") or self.config.get("openai_api_key")
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

RESEARCH STRATEGY - MIX ACADEMIC + PRACTICAL:

**{deep_topics} DEEP RESEARCH topics** (campaign mode, $1.50-2.50 each):
  SELECT FROM:
  - "academic": Research papers, theoretical foundations, seminal work
  - "technical-deep-dive": Architectural patterns, algorithms, design principles
  - "trends": Market analysis, future directions, industry evolution

  PURPOSE: Foundational knowledge that won't expire - the timeless insights

**{quick_topics} QUICK LOOKUP topics** (focus mode, $0.15-0.30 each):
  SELECT FROM:
  - "documentation": Latest APIs, SDKs, services, tools (2025 specific!)
  - "best-practices": Real-world implementation patterns, case studies
  - "trends": Quick scans of recent developments

  PURPOSE: Current, actionable knowledge - what's happening RIGHT NOW

CURRICULUM BALANCE (aim for this mix):
- 2-3 academic/research papers (deep) - Timeless foundations
- 2-3 technical deep dives (deep) - Core architectural knowledge
- 0-1 trend analysis (deep) - Future-looking synthesis
- 3-5 documentation (quick) - Latest tools, services, APIs
- 2-4 best practices (quick) - Real-world patterns

This creates an expert with BOTH:
- Deep theoretical understanding (won't age)
- Current practical knowledge (can be refreshed)

Total budget: ~${deep_topics * 2.0:.2f} (deep) + ~${quick_topics * 0.25:.2f} (quick) = ~${(deep_topics * 2.0) + (quick_topics * 0.25):.2f}
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

CURRICULUM REQUIREMENTS:

1. **Foundation First**: Start with core concepts and current landscape
2. **Multi-Dimensional Coverage**: Think in layers, not just linear topics:
   - Technical layers (data, app, network, security, infrastructure)
   - Implementation patterns (reference architectures, design patterns)
   - Technologies & tools (languages, frameworks, platforms)
   - Cross-cutting concerns (security, cost, compliance, observability)
3. **Current and Practical**: Focus on {today.split('-')[0]} best practices and real-world applications
4. **Progressive Depth**: Build from fundamentals to advanced topics
5. **Identify Gaps**: What's missing from the initial documents?
6. **Future-Oriented**: Include emerging trends and future directions

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
- research_prompt: The exact prompt to use for research (include year {today.split('-')[0]} for currency)
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

CRITICAL: Balance academic depth + current practical knowledge. This expert needs BOTH timeless principles AND 2025-specific tools!

EXAMPLE STRUCTURE (AWS Solutions Architect):
Instead of just "AWS Security", break it down:
- DEEP: Security frameworks & Zero Trust architecture (technical-deep-dive)
- QUICK: AWS WAF 2025 best practices (documentation)
- QUICK: Security at data layer (S3, RDS encryption patterns) (best-practices)
- QUICK: Security at app layer (API Gateway, Lambda IAM) (best-practices)
- QUICK: Python security patterns for AWS (best-practices)

This gives holistic, multi-dimensional coverage!

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
