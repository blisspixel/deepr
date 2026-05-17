"""Semantic citation validation for expert claims.

Validates whether sources actually support the claims they're cited for,
producing SupportClass ratings (SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / UNCERTAIN).

Usage:
    validator = CitationValidator()
    validations = await validator.validate_claims(claims, documents)
    summary = validator.summarize(validations)
"""

import logging
from typing import Any, Optional

from deepr.core.contracts import Claim, Source, SourceValidation, SupportClass

logger = logging.getLogger(__name__)

# Max claim-source pairs per LLM batch call
_BATCH_SIZE = 5


class CitationValidator:
    """Validates claim-source pairs for support classification.

    Attributes:
        client: OpenAI async client
        model: Model to use for validation
    """

    def __init__(self, client: Optional[Any] = None, model: str = "gpt-5.2"):
        self.client = client
        self.model = model

    async def _get_client(self):
        """Lazily initialize OpenAI client."""
        if self.client is None:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI()
        return self.client

    async def validate_claims(
        self,
        claims: list[Claim],
        documents: dict[str, str],
    ) -> list[SourceValidation]:
        """Validate all claim-source pairs.

        Args:
            claims: Claims to validate
            documents: Mapping of source title → content text

        Returns:
            List of SourceValidation results
        """
        # Collect all (claim, source) pairs
        pairs: list[tuple[Claim, Source, str]] = []
        for claim in claims:
            for source in claim.sources:
                # Look up source content by title match
                content = self._find_source_content(source, documents)
                if content:
                    pairs.append((claim, source, content))

        if not pairs:
            return []

        # Process in batches
        validations: list[SourceValidation] = []
        for i in range(0, len(pairs), _BATCH_SIZE):
            batch = pairs[i : i + _BATCH_SIZE]
            batch_results = await self._validate_batch(batch)
            validations.extend(batch_results)

        return validations

    async def _validate_batch(
        self,
        pairs: list[tuple[Claim, Source, str]],
    ) -> list[SourceValidation]:
        """Validate a batch of claim-source pairs with a single LLM call.

        Args:
            pairs: List of (Claim, Source, source_content) tuples

        Returns:
            List of SourceValidation results
        """
        # Build prompt
        prompt_parts = ["For each claim-source pair below, classify how well the source supports the claim.\n"]
        prompt_parts.append("Respond with a JSON array of objects, each with:")
        prompt_parts.append('  {"index": N, "support": "supported|partially_supported|unsupported|uncertain", ')
        prompt_parts.append('   "explanation": "brief reason"}\n')

        for i, (claim, source, content) in enumerate(pairs):
            prompt_parts.append(f"--- Pair {i} ---")
            prompt_parts.append(f"Claim: {claim.statement}")
            prompt_parts.append(f"Source [{source.title}]: {content[:800]}")
            prompt_parts.append("")

        prompt_parts.append("Output ONLY the JSON array, no other text.")
        prompt = "\n".join(prompt_parts)

        # Pre-flight cost-safety gate. Citation validation can fire many
        # paid LLM calls in a long-running expert workflow; without this
        # gate the daily / monthly budget is bypassed.
        try:
            from deepr.experts.cost_safety import get_cost_safety_manager

            cost_safety = get_cost_safety_manager()
            est_cost = 0.02  # gpt-5.2 batch validation; low reasoning effort
            allowed, deny_reason, _ = cost_safety.check_operation(
                session_id="citation_validator",
                operation_type="citation_validation",
                estimated_cost=est_cost,
                require_confirmation=False,
            )
            if not allowed:
                logger.warning("Citation validation blocked by cost-safety: %s", deny_reason)
                return [
                    SourceValidation(
                        source_id=src.id,
                        claim_id=claim.id,
                        support_class=SupportClass.UNCERTAIN,
                        explanation=f"Skipped: {deny_reason}",
                    )
                    for claim, src, _ in pairs
                ]
        except Exception:  # never let cost-safety bookkeeping mask the result
            cost_safety = None  # type: ignore[assignment]
            est_cost = 0.0

        try:
            client = await self._get_client()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You validate whether sources support claims. Output only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                reasoning_effort="low",
            )

            import json

            text = response.choices[0].message.content or "[]"
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            results = json.loads(text)

            validations = []
            for result in results:
                idx = result.get("index", 0)
                if 0 <= idx < len(pairs):
                    claim, source, _ = pairs[idx]
                    support_str = result.get("support", "uncertain")
                    try:
                        support = SupportClass(support_str)
                    except ValueError:
                        support = SupportClass.UNCERTAIN
                    validations.append(
                        SourceValidation(
                            source_id=source.id,
                            claim_id=claim.id,
                            support_class=support,
                            explanation=result.get("explanation", ""),
                        )
                    )

            # Settle the cost into the canonical ledger.
            if cost_safety is not None:
                try:
                    actual_cost = est_cost
                    if response.usage:
                        from deepr.experts.chat import _chat_token_cost as _tc

                        actual_cost = _tc(response.usage, self.model)
                    cost_safety.record_cost(
                        session_id="citation_validator",
                        operation_type="citation_validation",
                        actual_cost=float(actual_cost),
                        provider="openai",
                        model=self.model,
                        source="experts.citation_validator.validate_claims",
                    )
                except Exception:
                    pass

            return validations

        except Exception as e:
            logger.warning("Citation validation batch failed: %s", e)
            # Return UNCERTAIN for all pairs in batch
            return [
                SourceValidation(
                    source_id=source.id,
                    claim_id=claim.id,
                    support_class=SupportClass.UNCERTAIN,
                    explanation=f"Validation failed: {e}",
                )
                for claim, source, _ in pairs
            ]

    def _find_source_content(self, source: Source, documents: dict[str, str]) -> Optional[str]:
        """Find source content by title match.

        Args:
            source: Source to look up
            documents: Title → content mapping

        Returns:
            Content string or None
        """
        # Exact match
        if source.title in documents:
            return documents[source.title]

        # Case-insensitive match
        title_lower = source.title.lower()
        for doc_title, content in documents.items():
            if doc_title.lower() == title_lower:
                return content

        # Partial match (source title contained in doc title or vice versa)
        for doc_title, content in documents.items():
            if title_lower in doc_title.lower() or doc_title.lower() in title_lower:
                return content

        return None

    def summarize(self, validations: list[SourceValidation]) -> dict[str, Any]:
        """Produce a summary of validation results.

        Args:
            validations: List of SourceValidation results

        Returns:
            Summary dict with counts and support rate
        """
        total = len(validations)
        if total == 0:
            return {
                "total": 0,
                "supported": 0,
                "partially_supported": 0,
                "unsupported": 0,
                "uncertain": 0,
                "support_rate": 0.0,
                "flagged_claims": [],
            }

        counts = {
            SupportClass.SUPPORTED: 0,
            SupportClass.PARTIALLY_SUPPORTED: 0,
            SupportClass.UNSUPPORTED: 0,
            SupportClass.UNCERTAIN: 0,
        }
        for v in validations:
            counts[v.support_class] = counts.get(v.support_class, 0) + 1

        supported_count = counts[SupportClass.SUPPORTED] + counts[SupportClass.PARTIALLY_SUPPORTED] * 0.5
        support_rate = supported_count / total

        # Claims with unsupported sources
        flagged = list({v.claim_id for v in validations if v.support_class == SupportClass.UNSUPPORTED})

        return {
            "total": total,
            "supported": counts[SupportClass.SUPPORTED],
            "partially_supported": counts[SupportClass.PARTIALLY_SUPPORTED],
            "unsupported": counts[SupportClass.UNSUPPORTED],
            "uncertain": counts[SupportClass.UNCERTAIN],
            "support_rate": support_rate,
            "flagged_claims": flagged,
        }
