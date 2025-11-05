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

        # Use GPT-4 for curriculum planning (cost-effective, good at structured output)
        client = AsyncOpenAI(api_key=self.config.openai_api_key)

        completion = await client.chat.completions.create(
            model="gpt-4o",  # Fast, structured reasoning
            messages=[
                {"role": "system", "content": "You are an expert curriculum designer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,  # Allow some creativity
            max_tokens=4000
        )

        response = completion.choices[0].message.content

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
            budget_guidance = f"""
BUDGET CONSTRAINT: ${budget_limit:.2f}
- Estimated cost per research topic: $0.15-0.30 (focus mode)
- Stay within budget while maximizing learning value
- Prioritize foundational topics if budget is tight
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
2. **Current and Practical**: Focus on {today.split('-')[0]} best practices and real-world applications
3. **Progressive Depth**: Build from fundamentals to advanced topics
4. **Identify Gaps**: What's missing from the initial documents?
5. **Future-Oriented**: Include emerging trends and future directions

{budget_guidance}

TOPIC STRUCTURE:
For each topic, provide:
- title: Clear, specific topic name
- description: 1-2 sentences explaining what will be learned
- estimated_cost: $0.15 for quick topics, $0.30 for comprehensive
- estimated_minutes: 8-15 minutes per topic
- priority: 1 (critical foundation) to 5 (nice-to-have)
- research_prompt: The exact prompt to use for research (include year {today.split('-')[0]} for currency)
- dependencies: List of topic titles that should be researched first

OUTPUT FORMAT (JSON):
{{
  "topics": [
    {{
      "title": "Topic name",
      "description": "What will be learned",
      "estimated_cost": 0.20,
      "estimated_minutes": 10,
      "priority": 1,
      "research_prompt": "Research prompt with year {today.split('-')[0]}",
      "dependencies": []
    }}
  ]
}}

IMPORTANT GUIDELINES:
- Each research prompt should be specific and actionable
- Include year {today.split('-')[0]} in prompts for current information
- Estimated costs: $0.15 (quick), $0.20 (standard), $0.30 (comprehensive)
- Total topics: exactly {target_topics}
- Priority 1-2 topics are essential, 3-5 are supplementary
- Dependencies create logical learning flow

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
