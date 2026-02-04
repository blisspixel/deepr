"""
MCP Security Module.

Provides SSRF protection, domain allowlisting, request audit logging,
MCP sampling primitives, instruction signing, output verification,
and tool allowlisting for safe autonomous operation of the Deepr MCP server.
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
from .instruction_signing import (
    InstructionSigner,
    SignedInstruction,
    sign_instruction,
    verify_instruction,
)
from .output_verification import (
    OutputVerifier,
    VerifiedOutput,
    VerificationChainEntry,
)
from .tool_allowlist import (
    ToolAllowlist,
    ResearchMode,
    ToolCategory,
    ToolConfig,
    is_tool_allowed,
    get_allowed_tools,
)

__all__ = [
    # Network security
    "SSRFProtector",
    "is_internal_ip",
    # Sampling
    "SamplingRequest",
    "SamplingResponse",
    "SamplingReason",
    "create_captcha_request",
    "create_paywall_request",
    "create_confirmation_request",
    # Instruction signing
    "InstructionSigner",
    "SignedInstruction",
    "sign_instruction",
    "verify_instruction",
    # Output verification
    "OutputVerifier",
    "VerifiedOutput",
    "VerificationChainEntry",
    # Tool allowlist
    "ToolAllowlist",
    "ResearchMode",
    "ToolCategory",
    "ToolConfig",
    "is_tool_allowed",
    "get_allowed_tools",
]
