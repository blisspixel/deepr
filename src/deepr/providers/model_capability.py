"""Shared model capability contract for provider registries."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class ModelCapability:
    """Capability and pricing specification for one model route."""

    provider: str
    model: str
    cost_per_query: float
    latency_ms: int
    context_window: int
    specializations: list[str]
    strengths: list[str]
    weaknesses: list[str]
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0
    cached_input_cost_per_1m: float | None = None
    cache_write_cost_per_1m: float | None = None
    max_output_tokens: int | None = None
    deprecated: bool = False
    successor: str | None = None
    preview_only: bool = False
    access_state: Literal["unrestricted", "legacy_access_only"] = "unrestricted"
    access_source: str = ""
    access_checked: str = ""

    @property
    def selection_blocked(self) -> bool:
        """Exclude unavailable contracts without inventing provider deprecation."""
        return self.deprecated or self.access_state == "legacy_access_only"

    @property
    def access_note(self) -> str:
        """Provider policy is evidence about access, not account verification."""
        if self.access_state != "legacy_access_only":
            return ""
        return (
            f"{self.model}: prior users only; no announced shutdown. "
            "New projects: gemini-3.5-flash-lite or gemini-3.8-flash. "
            f"Account access unverified. Source: {self.access_source} (checked {self.access_checked})."
        )
