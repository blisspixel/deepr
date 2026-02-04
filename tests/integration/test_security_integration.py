"""Integration tests for execution security components."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from deepr.mcp.security.instruction_signing import InstructionSigner, SignedInstruction
from deepr.mcp.security.output_verification import OutputVerifier, VerifiedOutput
from deepr.mcp.security.tool_allowlist import ToolAllowlist, ResearchMode, ToolCategory


class TestSecurityPipelineIntegration:
    """Integration tests for the full security pipeline."""

    @pytest.mark.integration
    def test_full_tool_call_security_flow(self):
        """Test the complete security flow for a tool call."""
        # Initialize security components
        signer = InstructionSigner(key="integration-test-key")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "verification.db"
            verifier = OutputVerifier(db_path=db_path)
            allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

            # Step 1: Check if tool is allowed
            tool_name = "web_search"
            validation = allowlist.validate_tool_call(tool_name)

            assert validation["allowed"] is True
            assert validation["requires_confirmation"] is False

            # Step 2: Sign the instruction
            instruction = {
                "tool": tool_name,
                "arguments": {"query": "quantum computing applications"},
            }
            signed = signer.sign(instruction)

            assert isinstance(signed, SignedInstruction)
            assert signer.verify(signed, check_nonce=False) is True

            # Step 3: Execute tool (simulated)
            tool_output = {
                "results": [
                    {"title": "Quantum Computing Overview", "url": "https://example.com/1"},
                    {"title": "Applications of Qubits", "url": "https://example.com/2"},
                ],
                "total_results": 2,
            }

            # Step 4: Record and verify output
            verified = verifier.record_output(
                tool_name=tool_name,
                content=tool_output,
                job_id="test_job_123",
                metadata={
                    "instruction_nonce": signed.nonce,
                    "research_mode": allowlist.mode.value,
                },
            )

            assert verified.is_verified is True
            assert verified.job_id == "test_job_123"

            # Step 5: Verify the output matches
            verification_result = verifier.verify_output(verified.id, tool_output)
            assert verification_result.is_verified is True

            # Step 6: Verify chain integrity
            chain_result = verifier.verify_chain_integrity("test_job_123")
            assert chain_result["valid"] is True

            verifier.close()

    @pytest.mark.integration
    def test_blocked_tool_security_flow(self):
        """Test security flow when tool is blocked."""
        allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)

        # Try to use a write tool in read-only mode
        validation = allowlist.validate_tool_call("file_write")

        assert validation["allowed"] is False
        assert "blocked" in validation["reason"].lower()

    @pytest.mark.integration
    def test_tampered_output_detection(self):
        """Test detection of tampered outputs."""
        signer = InstructionSigner(key="tamper-test-key")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "verification.db"
            verifier = OutputVerifier(db_path=db_path)

            # Sign and record legitimate output
            instruction = {"tool": "analyze", "data": [1, 2, 3]}
            signed = signer.sign(instruction)

            original_output = {"analysis": "Result A", "confidence": 0.95}

            verified = verifier.record_output(
                tool_name="analyze",
                content=original_output,
                job_id="tamper_test",
            )

            # Attempt to verify with tampered output
            tampered_output = {"analysis": "Result B", "confidence": 0.95}

            verification = verifier.verify_output(verified.id, tampered_output)

            assert verification.is_verified is False
            assert "mismatch" in verification.verification_error.lower()

            verifier.close()

    @pytest.mark.integration
    def test_replay_attack_prevention(self):
        """Test that replay attacks are prevented."""
        signer = InstructionSigner(key="replay-test-key")

        instruction = {"tool": "sensitive_action", "target": "resource"}
        signed = signer.sign(instruction)

        # First use should succeed
        assert signer.verify(signed) is True

        # Replay attempt should fail
        assert signer.verify(signed) is False

    @pytest.mark.integration
    def test_expired_instruction_rejection(self):
        """Test that expired instructions are rejected."""
        import time

        signer = InstructionSigner(key="expiry-test-key", max_age_seconds=1)

        instruction = {"tool": "time_sensitive_action"}
        signed = signer.sign(instruction)

        # Should be valid immediately
        assert signer.is_expired(signed) is False

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        assert signer.is_expired(signed) is True

        # Combined check
        is_valid, is_expired, error = signer.verify_and_check_expiry(signed)
        assert is_valid is False
        assert is_expired is True


class TestMultiJobVerificationChains:
    """Integration tests for verification chains across multiple jobs."""

    @pytest.mark.integration
    def test_separate_chains_per_job(self):
        """Test that each job has its own verification chain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "verification.db"
            verifier = OutputVerifier(db_path=db_path)

            # Record outputs for job1
            verifier.record_output("tool1", {"data": "j1_1"}, job_id="job1")
            verifier.record_output("tool2", {"data": "j1_2"}, job_id="job1")

            # Record outputs for job2
            verifier.record_output("tool1", {"data": "j2_1"}, job_id="job2")

            # Get chains
            chain1 = verifier.get_verification_chain("job1")
            chain2 = verifier.get_verification_chain("job2")

            assert len(chain1) == 2
            assert len(chain2) == 1

            # Verify chain integrity separately
            result1 = verifier.verify_chain_integrity("job1")
            result2 = verifier.verify_chain_integrity("job2")

            assert result1["valid"] is True
            assert result2["valid"] is True

            verifier.close()

    @pytest.mark.integration
    def test_chain_links_correctly(self):
        """Test that chain entries link correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "verification.db"
            verifier = OutputVerifier(db_path=db_path)

            # Record sequence of outputs
            verifier.record_output("step1", {"phase": 1}, job_id="chain_job")
            verifier.record_output("step2", {"phase": 2}, job_id="chain_job")
            verifier.record_output("step3", {"phase": 3}, job_id="chain_job")

            chain = verifier.get_verification_chain("chain_job")

            # First entry has no previous
            assert chain[0].previous_hash is None
            assert chain[0].sequence == 1

            # Subsequent entries link to previous
            assert chain[1].previous_hash == chain[0].chain_hash
            assert chain[1].sequence == 2

            assert chain[2].previous_hash == chain[1].chain_hash
            assert chain[2].sequence == 3

            verifier.close()


class TestResearchModeTransitions:
    """Integration tests for research mode transitions."""

    @pytest.mark.integration
    def test_mode_escalation(self):
        """Test escalating from read_only to standard mode."""
        allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)

        # In read_only, file_write is blocked
        assert allowlist.is_allowed("file_write") is False

        # Escalate to standard mode
        allowlist.set_mode(ResearchMode.STANDARD)

        # Now file_write is allowed (with confirmation)
        assert allowlist.is_allowed("file_write") is True
        assert allowlist.require_confirmation("file_write") is True

    @pytest.mark.integration
    def test_mode_restriction(self):
        """Test restricting from unrestricted to read_only mode."""
        allowlist = ToolAllowlist(mode=ResearchMode.UNRESTRICTED)

        # Everything allowed in unrestricted
        assert allowlist.is_allowed("shell_command") is True
        assert allowlist.require_confirmation("shell_command") is False

        # Restrict to read_only
        allowlist.set_mode(ResearchMode.READ_ONLY)

        # shell_command now blocked
        assert allowlist.is_allowed("shell_command") is False

    @pytest.mark.integration
    def test_custom_tool_across_modes(self):
        """Test custom tool behavior across modes."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        # Register a custom tool that's only allowed in extended+
        allowlist.register_tool(
            name="dangerous_analysis",
            category=ToolCategory.EXECUTE,
            description="Potentially dangerous analysis",
            requires_confirmation_in={ResearchMode.EXTENDED},
            blocked_in={ResearchMode.READ_ONLY, ResearchMode.STANDARD},
        )

        # Blocked in standard
        assert allowlist.is_allowed("dangerous_analysis") is False

        # Allowed in extended
        allowlist.set_mode(ResearchMode.EXTENDED)
        assert allowlist.is_allowed("dangerous_analysis") is True
        assert allowlist.require_confirmation("dangerous_analysis") is True

        # Allowed without confirmation in unrestricted
        allowlist.set_mode(ResearchMode.UNRESTRICTED)
        assert allowlist.is_allowed("dangerous_analysis") is True
        assert allowlist.require_confirmation("dangerous_analysis") is False


class TestSecurityAuditTrail:
    """Integration tests for security audit trail."""

    @pytest.mark.integration
    def test_complete_audit_trail(self):
        """Test generating a complete audit trail for a research session."""
        signer = InstructionSigner(key="audit-test-key")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "verification.db"
            verifier = OutputVerifier(db_path=db_path)
            allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

            job_id = "audit_job_001"
            audit_entries = []

            # Simulate a research workflow
            tools_used = [
                ("web_search", {"query": "topic A"}),
                ("summarize", {"text": "long text..."}),
                ("web_search", {"query": "topic B"}),
                ("analyze", {"data": [1, 2, 3]}),
            ]

            for tool_name, args in tools_used:
                # Check permission
                validation = allowlist.validate_tool_call(tool_name)

                if validation["allowed"]:
                    # Sign instruction
                    instruction = {"tool": tool_name, "arguments": args}
                    signed = signer.sign(instruction)

                    # Simulate output
                    output = {"result": f"Output for {tool_name}", "success": True}

                    # Record output
                    verified = verifier.record_output(
                        tool_name=tool_name,
                        content=output,
                        job_id=job_id,
                        metadata={"nonce": signed.nonce},
                    )

                    audit_entries.append({
                        "tool": tool_name,
                        "nonce": signed.nonce,
                        "output_id": verified.id,
                        "content_hash": verified.content_hash,
                    })

            # Verify we have a complete audit trail
            assert len(audit_entries) == 4

            # Verify chain integrity
            chain = verifier.get_verification_chain(job_id)
            assert len(chain) == 4

            integrity = verifier.verify_chain_integrity(job_id)
            assert integrity["valid"] is True

            # Get statistics
            stats = verifier.get_stats(job_id=job_id)
            assert stats["total_outputs"] == 4
            assert stats["verification_rate"] == 1.0

            verifier.close()
