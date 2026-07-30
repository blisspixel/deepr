"""
Prompt Refinement Service

Automatically refines user research queries to follow best practices:
- Adds current date context for temporal queries
- Suggests structured deliverables
- Flags missing context needs
- Improves clarity and specificity
"""

import os
from datetime import datetime
from typing import Any, cast

from openai import OpenAI

_MAX_PROMPT_CHARS = 20_000
_MAX_COMPLETION_TOKENS = 1_200
_MAX_REFINEMENT_COST_USD = 0.25


class PromptRefiner:
    """
    Refines research prompts to follow best practices.

    Uses GPT-5-mini for fast, cheap prompt optimization.
    """

    def __init__(self, model: str = "gpt-5-mini"):
        """
        Initialize prompt refiner.

        Args:
            model: Model to use for refinement (gpt-5-mini recommended for speed/cost)
        """
        self.model = model
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required for PromptRefiner")
        self._api_key = api_key
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        """Construct the provider client only inside the reserved call."""
        if self._client is None:
            from deepr.providers.dispatch_authority import default_paid_endpoint

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=default_paid_endpoint("openai"),
                max_retries=0,
            )
        return self._client

    def refine(self, prompt: str, has_files: bool = False) -> dict[str, Any]:
        """
        Refine a research prompt to follow best practices.

        Args:
            prompt: Original user prompt
            has_files: Whether files are being uploaded with this research

        Returns:
            Dict with:
                - refined_prompt: Improved prompt
                - changes_made: List of improvements applied
                - original_prompt: Original for comparison
        """
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if len(prompt) > _MAX_PROMPT_CHARS:
            raise ValueError(f"prompt exceeds the {_MAX_PROMPT_CHARS:,}-character refinement limit")

        current_date = datetime.now().strftime("%B %Y")  # e.g., "October 2025"

        system_prompt = f"""You are a research prompt optimizer. Your job is to refine user research queries to follow best practices for deep research.

Current date: {current_date}

Best practices:
1. **Temporal context**: If query mentions "latest", "recent", "current", add explicit date context (e.g., "As of {current_date}...")
2. **Structured deliverables**: If scope is vague, suggest specific sections/analysis (e.g., "Include: (1) X, (2) Y, (3) Z")
3. **Clear scope**: Add specificity about timeframes, geography, industry segments if missing
4. **Best practices and current approaches**: For technology/methodology queries, explicitly request current best practices, latest approaches, and up-to-date information from trusted sources
5. **Quality sources**: Encourage the research to prioritize authoritative, recent sources (academic papers, official documentation, industry reports)
6. **Context flags**: If query seems business-specific but lacks context, note that context injection recommended
7. **Maintain intent**: Don't change the core question, only enhance clarity and structure

Files uploaded: {"Yes - user has provided documents for context" if has_files else "No"}

Output JSON format:
{{
  "refined_prompt": "The improved prompt (or same as original if no improvements needed)",
  "changes_made": ["List of specific improvements applied"],
  "needs_context": true/false,  // Does this need business context the user hasn't provided?
  "context_suggestion": "What context to add" or null
}}

If the prompt is already good (clear, specific, well-structured), return it unchanged with changes_made: ["No refinement needed - prompt already follows best practices"]"""

        user_prompt = f"""Original research prompt:
\"\"\"{prompt}\"\"\"

Refine this prompt to follow best practices. Focus on high-impact improvements that will lead to better research results.

Key considerations:
- Add temporal context (current date: {current_date})
- For technology/methodology topics, explicitly request current best practices and latest approaches
- Request prioritization of trusted, authoritative, up-to-date sources
- Add structured deliverables if scope is vague"""

        from deepr.services.metered_envelope import bounded_chat_envelope

        envelope = bounded_chat_envelope(
            provider="openai",
            model=self.model,
            prompt_parts=(system_prompt, user_prompt),
            budget_usd=_MAX_REFINEMENT_COST_USD,
            maximum_output_tokens=_MAX_COMPLETION_TOKENS,
            minimum_output_tokens=128,
        )
        from deepr.providers.dispatch_authority import require_official_paid_client
        from deepr.services.metered_call import execute_reserved_sync_call

        def dispatch() -> Any:
            client = self._get_client()
            require_official_paid_client(client, "openai")
            return client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=envelope.output_tokens,
                # GPT-5 models only support temperature=1 (default).
            )

        response = execute_reserved_sync_call(
            operation_prefix="prompt-refinement",
            provider="openai",
            model=self.model,
            source="services.prompt_refiner",
            max_cost_per_job=envelope.cost_usd,
            request_envelope={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "max_completion_tokens": envelope.output_tokens,
            },
            call=dispatch,
        )

        import json

        result = cast(dict[str, Any], json.loads(response.choices[0].message.content or "{}"))
        result["original_prompt"] = prompt

        return result
