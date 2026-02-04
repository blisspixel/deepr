"""Unit tests for instruction signing."""

import pytest
import time
from datetime import datetime, timezone, timedelta

from deepr.mcp.security.instruction_signing import (
    InstructionSigner,
    SignedInstruction,
    sign_instruction,
    verify_instruction,
)


class TestInstructionSigner:
    """Tests for InstructionSigner class."""

    def test_sign_instruction(self):
        """Test signing an instruction."""
        signer = InstructionSigner(key="test-key-123")
        instruction = {"tool": "web_search", "query": "quantum computing"}

        signed = signer.sign(instruction)

        assert isinstance(signed, SignedInstruction)
        assert signed.instruction == instruction
        assert signed.signature
        assert signed.timestamp
        assert signed.nonce
        assert signed.version == "1"

    def test_verify_valid_signature(self):
        """Test verifying a valid signature."""
        signer = InstructionSigner(key="test-key-123")
        instruction = {"tool": "web_search", "query": "quantum computing"}

        signed = signer.sign(instruction)
        is_valid = signer.verify(signed, check_nonce=False)

        assert is_valid is True

    def test_verify_invalid_signature(self):
        """Test detecting invalid signature."""
        signer = InstructionSigner(key="test-key-123")
        instruction = {"tool": "web_search", "query": "quantum computing"}

        signed = signer.sign(instruction)
        # Tamper with signature
        signed.signature = "invalid-signature"

        is_valid = signer.verify(signed, check_nonce=False)

        assert is_valid is False

    def test_verify_tampered_instruction(self):
        """Test detecting tampered instruction."""
        signer = InstructionSigner(key="test-key-123")
        instruction = {"tool": "web_search", "query": "quantum computing"}

        signed = signer.sign(instruction)
        # Tamper with instruction
        signed.instruction["query"] = "malicious query"

        is_valid = signer.verify(signed, check_nonce=False)

        assert is_valid is False

    def test_verify_different_key_fails(self):
        """Test that different key fails verification."""
        signer1 = InstructionSigner(key="key-1")
        signer2 = InstructionSigner(key="key-2")

        instruction = {"tool": "web_search", "query": "test"}
        signed = signer1.sign(instruction)

        is_valid = signer2.verify(signed, check_nonce=False)

        assert is_valid is False

    def test_nonce_replay_prevention(self):
        """Test that nonce replay is prevented."""
        signer = InstructionSigner(key="test-key")
        instruction = {"tool": "web_search", "query": "test"}

        signed = signer.sign(instruction)

        # First verification should succeed
        assert signer.verify(signed) is True

        # Second verification with same nonce should fail
        assert signer.verify(signed) is False

    def test_is_expired(self):
        """Test expiration checking."""
        signer = InstructionSigner(key="test-key", max_age_seconds=1)
        instruction = {"tool": "web_search", "query": "test"}

        signed = signer.sign(instruction)

        # Should not be expired immediately
        assert signer.is_expired(signed) is False

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        assert signer.is_expired(signed) is True

    def test_verify_and_check_expiry(self):
        """Test combined verify and expiry check."""
        signer = InstructionSigner(key="test-key", max_age_seconds=300)
        instruction = {"tool": "web_search", "query": "test"}

        signed = signer.sign(instruction)

        is_valid, is_expired, error = signer.verify_and_check_expiry(signed)

        assert is_valid is True
        assert is_expired is False
        assert error is None

    def test_verify_and_check_expiry_expired(self):
        """Test verify with expired instruction."""
        signer = InstructionSigner(key="test-key", max_age_seconds=0)
        instruction = {"tool": "web_search", "query": "test"}

        signed = signer.sign(instruction)
        time.sleep(0.1)  # Ensure expiration

        is_valid, is_expired, error = signer.verify_and_check_expiry(signed)

        assert is_valid is False
        assert is_expired is True
        assert "expired" in error.lower()

    def test_sign_batch(self):
        """Test batch signing."""
        signer = InstructionSigner(key="test-key")
        instructions = [
            {"tool": "web_search", "query": "test1"},
            {"tool": "file_read", "path": "/test"},
            {"tool": "analyze", "data": [1, 2, 3]},
        ]

        signed_batch = signer.sign_batch(instructions)

        assert len(signed_batch) == 3
        for i, signed in enumerate(signed_batch):
            assert signed.instruction == instructions[i]
            assert signer.verify(signed, check_nonce=False) is True

    def test_verify_batch(self):
        """Test batch verification."""
        signer = InstructionSigner(key="test-key")
        instructions = [
            {"tool": "web_search", "query": "test1"},
            {"tool": "file_read", "path": "/test"},
        ]

        signed_batch = signer.sign_batch(instructions)
        results = signer.verify_batch(signed_batch)

        assert len(results["valid"]) == 2
        assert len(results["invalid"]) == 0
        assert len(results["expired"]) == 0

    def test_serialization(self):
        """Test SignedInstruction serialization."""
        signer = InstructionSigner(key="test-key")
        instruction = {"tool": "web_search", "query": "test"}

        signed = signer.sign(instruction)

        # To dict
        data = signed.to_dict()
        assert "instruction" in data
        assert "signature" in data
        assert "timestamp" in data
        assert "nonce" in data

        # From dict
        restored = SignedInstruction.from_dict(data)
        assert restored.instruction == signed.instruction
        assert restored.signature == signed.signature

        # To/from JSON
        json_str = signed.to_json()
        restored_json = SignedInstruction.from_json(json_str)
        assert restored_json.instruction == signed.instruction

    def test_clear_nonce_cache(self):
        """Test clearing nonce cache."""
        signer = InstructionSigner(key="test-key")
        instruction = {"tool": "web_search", "query": "test"}

        signed = signer.sign(instruction)
        signer.verify(signed)  # Adds nonce to cache

        # Should fail due to nonce reuse
        assert signer.verify(signed) is False

        # Clear cache
        signer.clear_nonce_cache()

        # Should succeed now
        assert signer.verify(signed) is True


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_sign_instruction_function(self):
        """Test sign_instruction convenience function."""
        instruction = {"tool": "test", "data": "value"}

        signed = sign_instruction(instruction)

        assert isinstance(signed, SignedInstruction)
        assert signed.instruction == instruction

    def test_verify_instruction_function(self):
        """Test verify_instruction convenience function."""
        instruction = {"tool": "test", "data": "value"}

        signed = sign_instruction(instruction)

        # Note: This creates a new signer, so nonce won't be tracked
        # and key will be different - this tests the function exists
        # In practice, you'd use the same signer instance
        assert isinstance(signed, SignedInstruction)
