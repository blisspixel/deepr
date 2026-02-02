"""
MCP Security Module.

Provides SSRF protection, domain allowlisting, request audit logging,
and MCP sampling primitives for safe autonomous operation of the
Deepr MCP server.
"""

from .network import SSRFProtector, is_internal_ip
from .sampling import (
    SamplingRequest,
    SamplingResponse,
    SamplingReason,
    create_captcha_request,
    create_paywall_request,
    create_confirmation_request,
)

__all__ = [
    "SSRFProtector",
    "is_internal_ip",
    "SamplingRequest",
    "SamplingResponse",
    "SamplingReason",
    "create_captcha_request",
    "create_paywall_request",
    "create_confirmation_request",
]
