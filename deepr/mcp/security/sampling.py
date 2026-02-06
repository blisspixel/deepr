"""
MCP Sampling primitive for user confirmation flows.

When the research agent encounters a CAPTCHA, paywall, or other interactive
barrier, it can request human assistance via the MCP sampling flow rather
than silently failing.

Per MCP spec, sampling is a server-to-client request: the server asks the
client (Claude Desktop, OpenClaw, etc.) to present a prompt to the user.

This module defines the request/response shapes. Actual transport is
handled by the StdioServer notification mechanism.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SamplingReason(Enum):
    """Why the server is requesting user input."""

    CAPTCHA = "captcha"
    PAYWALL = "paywall"
    LOGIN_REQUIRED = "login_required"
    RATE_LIMITED = "rate_limited"
    CONFIRMATION = "confirmation"


@dataclass
class SamplingRequest:
    """A request from the server to the client for user input.

    Follows the MCP sampling/createMessage shape.
    """

    reason: SamplingReason
    prompt: str
    url: Optional[str] = None
    context: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 1024

    def to_mcp_params(self) -> dict:
        """Convert to MCP sampling/createMessage params."""
        messages = [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": self.prompt,
                },
            }
        ]

        return {
            "messages": messages,
            "maxTokens": self.max_tokens,
            "metadata": {
                "reason": self.reason.value,
                "url": self.url,
                **self.context,
            },
        }


@dataclass
class SamplingResponse:
    """Response from the client after user interaction."""

    content: str
    approved: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mcp_result(cls, result: dict) -> "SamplingResponse":
        """Parse from MCP sampling/createMessage result."""
        content_block = result.get("content", {})
        text = content_block.get("text", "") if isinstance(content_block, dict) else str(content_block)
        return cls(
            content=text,
            approved=result.get("stopReason") != "cancelled",
            metadata=result.get("metadata", {}),
        )


def create_captcha_request(url: str, description: str = "") -> SamplingRequest:
    """Create a sampling request for CAPTCHA resolution."""
    prompt = (
        f"The research agent encountered a CAPTCHA at: {url}\n\n"
        f"{description}\n\n"
        "Please solve the CAPTCHA and paste the result, "
        "or type 'skip' to skip this source."
    )
    return SamplingRequest(
        reason=SamplingReason.CAPTCHA,
        prompt=prompt,
        url=url,
    )


def create_paywall_request(url: str, title: str = "") -> SamplingRequest:
    """Create a sampling request for paywall confirmation."""
    prompt = (
        f"The research agent found a paywalled source:\n"
        f"  URL: {url}\n"
        f"  Title: {title}\n\n"
        "Would you like to:\n"
        "1. Skip this source\n"
        "2. Provide access credentials\n"
        "3. Paste the article content manually\n\n"
        "Reply with your choice or the content."
    )
    return SamplingRequest(
        reason=SamplingReason.PAYWALL,
        prompt=prompt,
        url=url,
        context={"title": title},
    )


def create_confirmation_request(action: str, details: str = "") -> SamplingRequest:
    """Create a sampling request for action confirmation."""
    prompt = (
        f"The research agent wants to perform an action that requires confirmation:\n\n"
        f"Action: {action}\n"
        f"{details}\n\n"
        "Reply 'yes' to approve or 'no' to deny."
    )
    return SamplingRequest(
        reason=SamplingReason.CONFIRMATION,
        prompt=prompt,
    )
