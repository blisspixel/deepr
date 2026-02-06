"""
MCP Security Module.

Provides SSRF protection, domain allowlisting, request audit logging,
MCP sampling primitives, instruction signing, output verification,
and tool allowlisting for safe autonomous operation of the Deepr MCP server.
"""

from .instruction_signing import (
    InstructionSigner,
    SignedInstruction,
    sign_instruction,
    verify_instruction,
)
from .network import SSRFProtector, is_internal_ip
from .output_verification import (
    OutputVerifier,
    VerificationChainEntry,
    VerifiedOutput,
)
from .sampling import (
    SamplingReason,
    SamplingRequest,
    SamplingResponse,
    create_captcha_request,
    create_confirmation_request,
    create_paywall_request,
)
from .tool_allowlist import (
    ResearchMode,
    ToolAllowlist,
    ToolCategory,
    ToolConfig,
    get_allowed_tools,
    is_tool_allowed,
)

__all__ = [
    # Instruction signing
    "InstructionSigner",
    # Output verification
    "OutputVerifier",
    "ResearchMode",
    # Network security
    "SSRFProtector",
    "SamplingReason",
    # Sampling
    "SamplingRequest",
    "SamplingResponse",
    "SignedInstruction",
    # Tool allowlist
    "ToolAllowlist",
    "ToolCategory",
    "ToolConfig",
    "VerificationChainEntry",
    "VerifiedOutput",
    "create_captcha_request",
    "create_confirmation_request",
    "create_paywall_request",
    "get_allowed_tools",
    "is_internal_ip",
    "is_tool_allowed",
    "sign_instruction",
    "verify_instruction",
]
