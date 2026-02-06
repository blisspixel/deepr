"""
Research Planner Service

Uses GPT-5 models (gpt-5, gpt-5-mini, gpt-5-nano) to decompose high-level scenarios
into multiple targeted research tasks. This is the "Prep" feature.

Example:
    User: "Meeting with Company X about Topic Y tomorrow"

    Planner generates:
    1. Research company background and recent news
    2. Research industry trends and use cases
    3. Research technical specifications for Topic Y
    4. Research competitor landscape
"""

import logging
import os
from typing import Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI

logger = logging.getLogger(__name__)


class ResearchPlanner:
    """
    Uses GPT-5 models to plan multi-angle research strategies.

    NO OLD MODELS - ONLY gpt-5, gpt-5-mini, gpt-5-nano allowed.
    """

    def __init__(
        self,
        model: str = "gpt-5",
        use_azure: bool = False,
        azure_endpoint: Optional[str] = None,
    ):
        """
        Initialize the research planner.

        Args:
            model: GPT-5 model to use (gpt-5, gpt-5-mini, gpt-5-nano)
            use_azure: Whether to use Azure OpenAI
            azure_endpoint: Azure OpenAI endpoint (if using Azure)
        """
        # Validate model is GPT-5 family only
        valid_models = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-chat"]
        if model not in valid_models:
            raise ValueError(f"Invalid model: {model}. Must be one of {valid_models}. NO OLD MODELS ALLOWED.")

        self.model = model
        self.use_azure = use_azure

        if use_azure and azure_endpoint:
            # Azure with Entra ID
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            )
            self.client = OpenAI(
                base_url=f"{azure_endpoint}/openai/v1/",
                api_key=token_provider,
            )
        elif use_azure:
            # Azure with API key
            self.client = OpenAI(
                base_url=f"{azure_endpoint}/openai/v1/",
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            )
        else:
            # OpenAI
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def plan_research(
        self,
        scenario: str,
        max_tasks: int = 5,
        context: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """
        Decompose a scenario into multiple research tasks.

        Args:
            scenario: High-level scenario (e.g., "Meeting with Company X about Topic Y")
            max_tasks: Maximum number of research tasks to generate (1-10)
            context: Optional additional context

        Returns:
            List of research task dictionaries with 'title' and 'prompt' keys
        """
        max_tasks = max(1, min(10, max_tasks))  # Clamp to 1-10

        system_prompt = """You are a research planning expert. Your job is to decompose high-level scenarios into specific, targeted research tasks WITH DEPENDENCIES and smart task mix.

Given a scenario, you will:
1. Analyze what information would be most valuable
2. Determine what needs to be DOCUMENTATION (facts) vs ANALYSIS (insights)
3. Organize tasks into phases based on dependencies
4. Create specific, actionable research prompts for each angle

SMART TASK MIX:

Documentation tasks (gather facts):
- Latest data, specifications, API docs, pricing
- Factual compilation, comprehensive reference materials
- Example: "Document the latest OpenAI pricing and rate limits as of 2025"
- Cheaper and faster (factual gathering)
- Use when you need factual foundation

Analysis tasks (generate insights):
- Trade-off analysis, evaluations, comparisons
- Strategic recommendations, synthesis
- Example: "Analyze cost-effectiveness of different LLM providers for batch processing"
- More expensive, benefits from having docs as context
- Use when you need insights and recommendations

COST-EFFECTIVE STRATEGY:
- Phase 1: Mix of documentation (facts) + foundational research (landscape)
- Phase 2: Analysis tasks that USE Phase 1 docs as context
- Phase 3: Synthesis that integrates facts AND insights
- Skip obvious information we likely already know
- Skip low-value research that won't help decision-making
- Balance comprehensive coverage with cost control

Task organization:
- Phase 1: Foundation (parallel - documentation + basic research)
- Phase 2: Analysis (depends on Phase 1 context)
- Phase 3: Synthesis (depends on all phases)

Return your response as a JSON array of objects with this structure:
[
  {
    "title": "Brief title (5-8 words)",
    "prompt": "Detailed research prompt (2-3 sentences)",
    "type": "documentation" or "analysis",
    "phase": 1,
    "depends_on": []  // empty for phase 1, task numbers for later phases
  }
]

Example:
[
  {"title": "Latest EV sales data", "prompt": "Document latest EV sales numbers and projections for 2025", "type": "documentation", "model": "o4-mini-deep-research", "phase": 1, "depends_on": []},
  {"title": "Key players market share", "prompt": "Document market share and financials for top EV manufacturers", "type": "documentation", "model": "o4-mini-deep-research", "phase": 1, "depends_on": []},
  {"title": "Technology landscape", "prompt": "Research battery tech and charging infrastructure trends", "type": "analysis", "model": "o4-mini-deep-research", "phase": 1, "depends_on": []},
  {"title": "Competitive dynamics", "prompt": "Using market data and player profiles, analyze competitive dynamics and strategic positioning", "type": "analysis", "model": "o3-deep-research", "phase": 2, "depends_on": [1,2]},
  {"title": "Strategic synthesis", "prompt": "Synthesize all findings into strategic implications", "type": "analysis", "model": "o3-deep-research", "phase": 3, "depends_on": [1,2,3,4]}
]

MODEL SELECTION RULES:
- Documentation (facts): Use o4-mini-deep-research (fast, cheap, sufficient for factual gathering)
- Simple analysis: Use o4-mini-deep-research (good for straightforward comparisons)
- Deep analysis: Use o3-deep-research (thorough reasoning, complex trade-offs)
- Synthesis: Use o3-deep-research (integrates multiple sources, strategic insights)

Be thorough but cost-conscious. Maximum value, zero waste."""

        user_prompt = f"""Scenario: {scenario}

Max research tasks: {max_tasks}"""

        if context:
            user_prompt += f"\n\nAdditional context: {context}"

        user_prompt += f"""

Please analyze this scenario and generate {max_tasks} distinct research tasks that would provide comprehensive preparation. Return ONLY a JSON array, no other text."""

        try:
            response = self.client.responses.create(
                model=self.model,
                input=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                # Note: GPT-5 reasoning models don't support temperature parameter
            )

            # Extract the response text
            response_text = response.output_text if hasattr(response, "output_text") else ""

            # If output is a list, get text from first message
            if not response_text and hasattr(response, "output") and response.output:
                for item in response.output:
                    if hasattr(item, "type") and item.type == "message":
                        for content in item.content:
                            if hasattr(content, "type") and content.type == "output_text":
                                response_text = content.text
                                break

            # Parse JSON response
            import json

            # Try to extract JSON from response
            # Sometimes models wrap it in markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            tasks = json.loads(response_text)

            # Validate structure
            if not isinstance(tasks, list):
                raise ValueError("Response is not a list")

            validated_tasks = []
            for task in tasks[:max_tasks]:  # Ensure we don't exceed max_tasks
                if isinstance(task, dict) and "title" in task and "prompt" in task:
                    validated_tasks.append(
                        {
                            "title": str(task["title"])[:100],  # Cap title length
                            "prompt": str(task["prompt"])[:1000],  # Cap prompt length
                        }
                    )

            if not validated_tasks:
                raise ValueError("No valid tasks in response")

            return validated_tasks

        except Exception as e:
            # Fallback: generate basic research tasks
            logger.error("Error planning research: %s", e)
            return self._fallback_plan(scenario, max_tasks)

    def _fallback_plan(self, scenario: str, max_tasks: int) -> list[dict[str, str]]:
        """
        Fallback plan if GPT-5 call fails.
        Generates generic but useful research tasks.
        """
        # Basic research angles
        tasks = [
            {
                "title": "Background and Overview Research",
                "prompt": f"Research comprehensive background information about: {scenario}. Include recent news, key developments, and current status.",
            },
            {
                "title": "Industry Context and Trends",
                "prompt": f"Research industry trends, market dynamics, and broader context related to: {scenario}.",
            },
            {
                "title": "Technical Deep Dive",
                "prompt": f"Research technical specifications, implementation details, and technical considerations for: {scenario}.",
            },
            {
                "title": "Competitive Landscape",
                "prompt": f"Research competitors, alternatives, and comparative analysis relevant to: {scenario}.",
            },
            {
                "title": "Use Cases and Applications",
                "prompt": f"Research real-world use cases, applications, and practical examples related to: {scenario}.",
            },
        ]

        return tasks[:max_tasks]


def create_planner(
    model: str = "gpt-5-mini",
    provider: str = "openai",
    azure_endpoint: Optional[str] = None,
) -> ResearchPlanner:
    """
    Factory function to create a research planner.

    Args:
        model: GPT-5 model (gpt-5, gpt-5-mini, gpt-5-nano)
        provider: 'openai' or 'azure'
        azure_endpoint: Azure endpoint if using Azure

    Returns:
        Configured ResearchPlanner instance
    """
    use_azure = provider.lower() == "azure"
    return ResearchPlanner(
        model=model,
        use_azure=use_azure,
        azure_endpoint=azure_endpoint,
    )
