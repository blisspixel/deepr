"""Instruction signing for MCP tool calls.

Signs instructions sent to MCP tools to ensure authenticity and
prevent tampering or replay attacks.

Usage:
    from deepr.mcp.security.instruction_signing import InstructionSigner

    signer = InstructionSigner()

    # Sign an instruction
    signed = signer.sign({"tool": "web_search", "query": "quantum computing"})

    # Verify signature
    if signer.verify(signed):
        print("Instruction is authentic")

    # Check expiration
    if signer.is_expired(signed, max_age_seconds=300):
        print("Instruction has expired")
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


# Environment variable for signing key
SIGNING_KEY_ENV = "DEEPR_SIGNING_KEY"

# Default max age for instructions (5 minutes)
DEFAULT_MAX_AGE = 300


@dataclass
class SignedInstruction:
    """A signed instruction for MCP tool calls."""

    instruction: Dict[str, Any]
    signature: str
    timestamp: str
    nonce: str
    version: str = "1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instruction": self.instruction,
            "signature": self.signature,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignedInstruction":
        return cls(
            instruction=data["instruction"],
            signature=data["signature"],
            timestamp=data["timestamp"],
            nonce=data["nonce"],
            version=data.get("version", "1"),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, json_str: str) -> "SignedInstruction":
        return cls.from_dict(json.loads(json_str))


class InstructionSigner:
    """Signs and verifies MCP tool instructions.

    Uses HMAC-SHA256 for signing with a secret key.

    Attributes:
        key: Signing key (from environment or generated)
    """

    def __init__(
        self,
        key: Optional[str] = None,
        max_age_seconds: int = DEFAULT_MAX_AGE,
    ):
        """Initialize the signer.

        Args:
            key: Signing key (uses env var or generates if not provided)
            max_age_seconds: Default max age for instructions
        """
        self._key = key or os.environ.get(SIGNING_KEY_ENV) or self._generate_key()
        self._key_bytes = self._key.encode("utf-8")
        self.max_age_seconds = max_age_seconds

        # Track used nonces to prevent replay attacks
        self._used_nonces: set = set()
        self._nonce_cleanup_threshold = 10000

    def sign(
        self,
        instruction: Dict[str, Any],
    ) -> SignedInstruction:
        """Sign an instruction.

        Args:
            instruction: Instruction to sign

        Returns:
            SignedInstruction with signature
        """
        timestamp = _utc_now().isoformat()
        nonce = self._generate_nonce()

        # Create canonical representation
        canonical = self._canonicalize(instruction, timestamp, nonce)

        # Generate signature
        signature = self._compute_signature(canonical)

        return SignedInstruction(
            instruction=instruction,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )

    def verify(
        self,
        signed: SignedInstruction,
        check_nonce: bool = True,
    ) -> bool:
        """Verify a signed instruction.

        Args:
            signed: SignedInstruction to verify
            check_nonce: Whether to check for nonce reuse

        Returns:
            True if signature is valid
        """
        # Check nonce reuse
        if check_nonce:
            if signed.nonce in self._used_nonces:
                return False

        # Recreate canonical representation
        canonical = self._canonicalize(
            signed.instruction,
            signed.timestamp,
            signed.nonce,
        )

        # Compute expected signature
        expected = self._compute_signature(canonical)

        # Constant-time comparison
        is_valid = hmac.compare_digest(signed.signature, expected)

        # Track nonce if valid
        if is_valid and check_nonce:
            self._track_nonce(signed.nonce)

        return is_valid

    def is_expired(
        self,
        signed: SignedInstruction,
        max_age_seconds: Optional[int] = None,
    ) -> bool:
        """Check if a signed instruction has expired.

        Args:
            signed: SignedInstruction to check
            max_age_seconds: Override max age

        Returns:
            True if instruction has expired
        """
        max_age = max_age_seconds or self.max_age_seconds

        try:
            instruction_time = datetime.fromisoformat(signed.timestamp)
            if instruction_time.tzinfo is None:
                instruction_time = instruction_time.replace(tzinfo=timezone.utc)

            now = _utc_now()
            age = (now - instruction_time).total_seconds()

            return age > max_age

        except (ValueError, TypeError):
            # Invalid timestamp
            return True

    def verify_and_check_expiry(
        self,
        signed: SignedInstruction,
        max_age_seconds: Optional[int] = None,
    ) -> tuple:
        """Verify signature and check expiration.

        Args:
            signed: SignedInstruction to verify
            max_age_seconds: Override max age

        Returns:
            Tuple of (is_valid, is_expired, error_message)
        """
        # Check expiration first (cheaper)
        if self.is_expired(signed, max_age_seconds):
            return False, True, "Instruction has expired"

        # Verify signature
        if not self.verify(signed):
            return False, False, "Invalid signature"

        return True, False, None

    def sign_batch(
        self,
        instructions: list,
    ) -> list:
        """Sign a batch of instructions.

        Args:
            instructions: List of instructions to sign

        Returns:
            List of SignedInstruction objects
        """
        return [self.sign(inst) for inst in instructions]

    def verify_batch(
        self,
        signed_instructions: list,
    ) -> dict:
        """Verify a batch of signed instructions.

        Args:
            signed_instructions: List of SignedInstruction objects

        Returns:
            Dict with verification results
        """
        results = {
            "valid": [],
            "invalid": [],
            "expired": [],
        }

        for signed in signed_instructions:
            is_valid, is_expired, error = self.verify_and_check_expiry(signed)

            if is_expired:
                results["expired"].append(signed.nonce)
            elif not is_valid:
                results["invalid"].append(signed.nonce)
            else:
                results["valid"].append(signed.nonce)

        return results

    def _canonicalize(
        self,
        instruction: Dict[str, Any],
        timestamp: str,
        nonce: str,
    ) -> str:
        """Create canonical string for signing.

        Args:
            instruction: Instruction dict
            timestamp: ISO timestamp
            nonce: Unique nonce

        Returns:
            Canonical string
        """
        # Sort keys for consistent representation
        canonical_instruction = json.dumps(instruction, sort_keys=True, separators=(",", ":"))

        return f"{canonical_instruction}|{timestamp}|{nonce}"

    def _compute_signature(self, data: str) -> str:
        """Compute HMAC-SHA256 signature.

        Args:
            data: Data to sign

        Returns:
            Base64-encoded signature
        """
        signature = hmac.new(
            self._key_bytes,
            data.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        return base64.b64encode(signature).decode("utf-8")

    def _generate_nonce(self) -> str:
        """Generate a unique nonce.

        Returns:
            Random nonce string
        """
        return secrets.token_hex(16)

    def _generate_key(self) -> str:
        """Generate a new signing key.

        Returns:
            Random key string
        """
        return secrets.token_hex(32)

    def _track_nonce(self, nonce: str):
        """Track a used nonce.

        Args:
            nonce: Nonce to track
        """
        self._used_nonces.add(nonce)

        # Cleanup if too many nonces
        if len(self._used_nonces) > self._nonce_cleanup_threshold:
            # Keep most recent half
            nonces_list = list(self._used_nonces)
            self._used_nonces = set(nonces_list[len(nonces_list) // 2 :])

    def clear_nonce_cache(self):
        """Clear the nonce tracking cache."""
        self._used_nonces.clear()


# Convenience functions


def sign_instruction(instruction: Dict[str, Any]) -> SignedInstruction:
    """Sign an instruction using default signer.

    Args:
        instruction: Instruction to sign

    Returns:
        SignedInstruction
    """
    signer = InstructionSigner()
    return signer.sign(instruction)


def verify_instruction(signed: SignedInstruction) -> bool:
    """Verify a signed instruction using default signer.

    Args:
        signed: SignedInstruction to verify

    Returns:
        True if valid
    """
    signer = InstructionSigner()
    return signer.verify(signed)
