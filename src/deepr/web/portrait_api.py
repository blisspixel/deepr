"""Expert portrait web endpoint implementation."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping, MutableMapping, Set
from pathlib import Path
from typing import Any

from flask import jsonify

from deepr.experts.portrait_cost_gate import (
    PortraitCostBlocked,
    record_portrait_cost,
    refund_portrait_cost,
    reserve_portrait_cost,
)

logger = logging.getLogger(__name__)


def generate_expert_portrait_response(
    *,
    decoded_name: str,
    experts_dir: Path,
    portraits_dir: Path,
    request_data: object,
    last_generated: MutableMapping[str, float],
    allowed_providers: Set[str],
    cooldown_seconds: int,
) -> Any:
    """Generate or replace one expert portrait under no-surprise-cost gates."""
    try:
        from deepr.experts.portraits import detect_provider, generate_portrait, portrait_cost
        from deepr.experts.profile_store import ExpertStore

        store = ExpertStore(str(experts_dir))
        if not store.exists(decoded_name):
            return jsonify({"error": "Expert not found"}), 404

        profile = store.load(decoded_name)
        data: Mapping[str, Any] = request_data if isinstance(request_data, Mapping) else {}
        provider = data.get("provider")
        if provider is not None and provider not in allowed_providers:
            return jsonify({"error": f"Invalid provider. Allowed: {sorted(allowed_providers)}"}), 400

        existing_portrait_url = getattr(profile, "portrait_url", None)
        if existing_portrait_url and not bool(data.get("force")):
            return jsonify(
                {
                    "error": "Portrait already exists. Pass force=true to regenerate.",
                    "portrait_url": existing_portrait_url,
                }
            ), 409

        wait = cooldown_seconds - (time.monotonic() - last_generated.get(decoded_name, 0.0))
        if wait > 0:
            return jsonify(
                {
                    "error": "Portrait was generated recently. Try again later.",
                    "retry_after_seconds": int(wait) + 1,
                }
            ), 429

        effective_provider = provider or detect_provider()
        if not effective_provider:
            return jsonify({"error": "No image generator available"}), 400

        estimated_cost = portrait_cost(effective_provider)
        if estimated_cost > 0 and data.get("confirm_metered_cost") is not True:
            return jsonify(
                {
                    "error": "Metered portrait generation requires explicit cost confirmation.",
                    "provider": effective_provider,
                    "estimated_cost_usd": estimated_cost,
                }
            ), 402
        if estimated_cost > 0:
            from deepr.experts.metered_mutation_gate import (
                MeteredExpertMutationDisabledError,
                require_metered_expert_mutation,
            )
            from deepr.web.metered_expert_gate import metered_expert_mutation_block

            safe_alternative = "set DEEPR_LOCAL_IMAGE_URL and request provider=local"
            try:
                require_metered_expert_mutation("api_expert_portrait", safe_alternative=safe_alternative)
            except MeteredExpertMutationDisabledError:
                payload, status = metered_expert_mutation_block(
                    "api_expert_portrait", safe_alternative=safe_alternative
                )
                return jsonify(payload), status

        try:
            cost_reservation = reserve_portrait_cost(
                expert_name=decoded_name,
                provider=effective_provider,
                detect_provider=detect_provider,
                portrait_cost=portrait_cost,
            )
        except PortraitCostBlocked:
            return jsonify({"error": "Portrait generation blocked by cost safety."}), 402

        loop = asyncio.new_event_loop()
        try:
            portrait_url = loop.run_until_complete(
                generate_portrait(
                    name=profile.name,
                    domain=getattr(profile, "domain", None),
                    description=getattr(profile, "description", None),
                    provider=cost_reservation.effective_provider,
                    output_dir=str(portraits_dir),
                )
            )
        except Exception as exc:
            refund_portrait_cost(cost_reservation)
            logger.warning("Portrait generation failed for %s with %s", decoded_name, type(exc).__name__)
            return jsonify({"error": "Portrait generation failed"}), 500
        finally:
            loop.close()

        record_portrait_cost(
            expert_name=decoded_name,
            reservation=cost_reservation,
            source="web.generate_expert_portrait",
        )
        last_generated[decoded_name] = time.monotonic()
        profile.portrait_url = portrait_url
        store.save(profile)
        return jsonify({"portrait_url": portrait_url})
    except RuntimeError as e:
        logger.warning("Portrait generation failed for %s: %s", decoded_name, e)
        return jsonify({"error": "Portrait generation failed"}), 400
    except Exception as e:
        logger.error("Error generating portrait for %s: %s", decoded_name, e)
        return jsonify({"error": "Portrait generation failed"}), 500
