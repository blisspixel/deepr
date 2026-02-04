"""Unit tests for output verification."""

import pytest
import tempfile
from pathlib import Path

from deepr.mcp.security.output_verification import (
    OutputVerifier,
    VerifiedOutput,
    VerificationChainEntry,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_verification.db"
        yield db_path


@pytest.fixture
def verifier(temp_db):
    """Create an OutputVerifier instance."""
    v = OutputVerifier(db_path=temp_db)
    yield v
    v.close()


class TestOutputVerifier:
    """Tests for OutputVerifier class."""

    def test_record_output(self, verifier):
        """Test recording a tool output."""
        result = verifier.record_output(
            tool_name="web_search",
            content={"results": ["result1", "result2"]},
        )

        assert isinstance(result, VerifiedOutput)
        assert result.tool_name == "web_search"
        assert result.content_hash
        assert result.is_verified is True
        assert result.id.startswith("out_")

    def test_record_output_with_job_id(self, verifier):
        """Test recording output with job ID."""
        result = verifier.record_output(
            tool_name="web_search",
            content={"results": ["result1"]},
            job_id="job123",
        )

        assert result.job_id == "job123"

    def test_record_output_with_metadata(self, verifier):
        """Test recording output with metadata."""
        result = verifier.record_output(
            tool_name="web_search",
            content={"results": ["result1"]},
            metadata={"nonce": "abc123", "mode": "standard"},
        )

        assert result.metadata == {"nonce": "abc123", "mode": "standard"}

    def test_verify_output_valid(self, verifier):
        """Test verifying output with matching content."""
        content = {"results": ["result1", "result2"]}

        recorded = verifier.record_output(
            tool_name="web_search",
            content=content,
        )

        verified = verifier.verify_output(recorded.id, content)

        assert verified.is_verified is True
        assert verified.verification_error is None

    def test_verify_output_tampered(self, verifier):
        """Test detecting tampered output."""
        original_content = {"results": ["result1", "result2"]}
        tampered_content = {"results": ["result1", "malicious"]}

        recorded = verifier.record_output(
            tool_name="web_search",
            content=original_content,
        )

        verified = verifier.verify_output(recorded.id, tampered_content)

        assert verified.is_verified is False
        assert "mismatch" in verified.verification_error.lower()

    def test_verify_output_not_found(self, verifier):
        """Test verifying non-existent output."""
        verified = verifier.verify_output("nonexistent_id", {"data": "test"})

        assert verified.is_verified is False
        assert "not found" in verified.verification_error.lower()

    def test_get_output(self, verifier):
        """Test retrieving output by ID."""
        recorded = verifier.record_output(
            tool_name="test_tool",
            content={"value": 42},
        )

        retrieved = verifier.get_output(recorded.id)

        assert retrieved is not None
        assert retrieved.id == recorded.id
        assert retrieved.tool_name == "test_tool"
        assert retrieved.content_hash == recorded.content_hash

    def test_get_output_not_found(self, verifier):
        """Test retrieving non-existent output."""
        result = verifier.get_output("nonexistent")

        assert result is None

    def test_get_outputs_for_job(self, verifier):
        """Test retrieving all outputs for a job."""
        job_id = "job456"

        # Record multiple outputs for same job
        verifier.record_output("tool1", {"data": 1}, job_id=job_id)
        verifier.record_output("tool2", {"data": 2}, job_id=job_id)
        verifier.record_output("tool3", {"data": 3}, job_id=job_id)

        # Record output for different job
        verifier.record_output("tool4", {"data": 4}, job_id="other_job")

        outputs = verifier.get_outputs_for_job(job_id)

        assert len(outputs) == 3
        for output in outputs:
            assert output.job_id == job_id


class TestVerificationChain:
    """Tests for verification chain functionality."""

    def test_chain_created_for_job(self, verifier):
        """Test that chain entries are created for job outputs."""
        job_id = "chain_job"

        verifier.record_output("tool1", {"data": 1}, job_id=job_id)
        verifier.record_output("tool2", {"data": 2}, job_id=job_id)
        verifier.record_output("tool3", {"data": 3}, job_id=job_id)

        chain = verifier.get_verification_chain(job_id)

        assert len(chain) == 3
        assert chain[0].sequence == 1
        assert chain[1].sequence == 2
        assert chain[2].sequence == 3

    def test_chain_links_correctly(self, verifier):
        """Test that chain entries link correctly."""
        job_id = "link_job"

        verifier.record_output("tool1", {"data": 1}, job_id=job_id)
        verifier.record_output("tool2", {"data": 2}, job_id=job_id)

        chain = verifier.get_verification_chain(job_id)

        # First entry should have no previous hash
        assert chain[0].previous_hash is None

        # Second entry should reference first entry's chain hash
        assert chain[1].previous_hash == chain[0].chain_hash

    def test_verify_chain_integrity_valid(self, verifier):
        """Test verifying valid chain."""
        job_id = "valid_chain"

        verifier.record_output("tool1", {"data": 1}, job_id=job_id)
        verifier.record_output("tool2", {"data": 2}, job_id=job_id)

        result = verifier.verify_chain_integrity(job_id)

        assert result["valid"] is True
        assert result["error"] is None
        assert result["chain_length"] == 2

    def test_verify_chain_empty(self, verifier):
        """Test verifying empty chain."""
        result = verifier.verify_chain_integrity("nonexistent_job")

        assert result["valid"] is True
        assert result["chain_length"] == 0

    def test_chain_entry_serialization(self, verifier):
        """Test VerificationChainEntry serialization."""
        job_id = "serial_job"

        verifier.record_output("tool1", {"data": 1}, job_id=job_id)
        chain = verifier.get_verification_chain(job_id)

        data = chain[0].to_dict()

        assert "output_id" in data
        assert "content_hash" in data
        assert "chain_hash" in data
        assert "sequence" in data
        assert "timestamp" in data


class TestVerifiedOutput:
    """Tests for VerifiedOutput dataclass."""

    def test_to_dict(self, verifier):
        """Test VerifiedOutput.to_dict()."""
        output = verifier.record_output(
            tool_name="test",
            content={"value": 1},
            job_id="job1",
            metadata={"key": "value"},
        )

        data = output.to_dict()

        assert data["id"] == output.id
        assert data["tool_name"] == "test"
        assert data["job_id"] == "job1"
        assert data["is_verified"] is True
        assert data["metadata"] == {"key": "value"}
        assert "timestamp" in data
        assert "content_hash" in data


class TestStatistics:
    """Tests for verification statistics."""

    def test_get_stats_empty(self, verifier):
        """Test stats with no outputs."""
        stats = verifier.get_stats()

        assert stats["total_outputs"] == 0
        assert stats["verified_outputs"] == 0
        assert stats["failed_verification"] == 0
        assert stats["verification_rate"] == 1.0

    def test_get_stats_all_verified(self, verifier):
        """Test stats with all verified outputs."""
        verifier.record_output("tool1", {"data": 1})
        verifier.record_output("tool2", {"data": 2})
        verifier.record_output("tool3", {"data": 3})

        stats = verifier.get_stats()

        assert stats["total_outputs"] == 3
        assert stats["verified_outputs"] == 3
        assert stats["failed_verification"] == 0
        assert stats["verification_rate"] == 1.0

    def test_get_stats_with_failures(self, verifier):
        """Test stats after verification failures."""
        output = verifier.record_output("tool1", {"data": 1})
        verifier.record_output("tool2", {"data": 2})

        # Cause verification failure
        verifier.verify_output(output.id, {"data": "tampered"})

        stats = verifier.get_stats()

        assert stats["total_outputs"] == 2
        assert stats["verified_outputs"] == 1
        assert stats["failed_verification"] == 1
        assert stats["verification_rate"] == 0.5

    def test_get_stats_for_job(self, verifier):
        """Test stats filtered by job."""
        verifier.record_output("tool1", {"data": 1}, job_id="job1")
        verifier.record_output("tool2", {"data": 2}, job_id="job1")
        verifier.record_output("tool3", {"data": 3}, job_id="job2")

        stats = verifier.get_stats(job_id="job1")

        assert stats["total_outputs"] == 2


class TestHashConsistency:
    """Tests for hash consistency."""

    def test_same_content_same_hash(self, verifier):
        """Test that same content produces same hash."""
        content = {"results": ["a", "b", "c"], "count": 3}

        output1 = verifier.record_output("tool", content)
        output2 = verifier.record_output("tool", content)

        assert output1.content_hash == output2.content_hash

    def test_different_content_different_hash(self, verifier):
        """Test that different content produces different hash."""
        output1 = verifier.record_output("tool", {"value": 1})
        output2 = verifier.record_output("tool", {"value": 2})

        assert output1.content_hash != output2.content_hash

    def test_key_order_independent(self, verifier):
        """Test that dict key order doesn't affect hash."""
        content1 = {"a": 1, "b": 2, "c": 3}
        content2 = {"c": 3, "a": 1, "b": 2}

        output1 = verifier.record_output("tool", content1)
        output2 = verifier.record_output("tool", content2)

        assert output1.content_hash == output2.content_hash
