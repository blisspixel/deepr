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
from .scoped_keys import (
    RemoteMCPAuditEvent,
    RemoteMCPAuditLog,
    ScopedMCPAuthzDecision,
    ScopedMCPKeyContext,
    ScopedMCPKeyRecord,
    ScopedMCPKeyStore,
    authorize_scoped_mcp_tool_call,
    default_key_store_path,
    default_remote_audit_path,
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
    "InstructionSigner",
    "OutputVerifier",
    "RemoteMCPAuditEvent",
    "RemoteMCPAuditLog",
    "ResearchMode",
    "SSRFProtector",
    "SamplingReason",
    "SamplingRequest",
    "SamplingResponse",
    "ScopedMCPAuthzDecision",
    "ScopedMCPKeyContext",
    "ScopedMCPKeyRecord",
    "ScopedMCPKeyStore",
    "SignedInstruction",
    "ToolAllowlist",
    "ToolCategory",
    "ToolConfig",
    "VerificationChainEntry",
    "VerifiedOutput",
    "authorize_scoped_mcp_tool_call",
    "create_captcha_request",
    "create_confirmation_request",
    "create_paywall_request",
    "default_key_store_path",
    "default_remote_audit_path",
    "get_allowed_tools",
    "is_internal_ip",
    "is_tool_allowed",
    "sign_instruction",
    "verify_instruction",
]
