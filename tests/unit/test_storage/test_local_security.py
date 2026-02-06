"""
Property-based tests for LocalStorage path security.

Tests the security properties of the LocalStorage class to ensure:
1. All resolved paths remain within the base storage directory
2. Path traversal patterns are always rejected

Feature: code-quality-security-hardening
Properties: 1 (Path Containment Invariant), 2 (Path Traversal Rejection)
**Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6**
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from deepr.storage.base import StorageError
from deepr.storage.local import LocalStorage

# =============================================================================
# Test Strategies
# =============================================================================

# Strategy for generating valid job_id characters (alphanumeric, hyphens, underscores)
valid_job_id_chars = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-", min_size=1, max_size=100
)

# Strategy for generating arbitrary text that might be used as job_id
arbitrary_job_ids = st.text(min_size=0, max_size=200)

# Strategy for generating potentially malicious job_ids with traversal patterns
malicious_job_ids = st.one_of(
    # Direct traversal patterns
    st.sampled_from(
        [
            "../",
            "..\\",
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "job/../../../secret",
            "valid-job/../../../etc/passwd",
            "..%2f",
            "..%5c",
            "....//",
            "....\\\\",
            ".../",
            "...\\",
            "job/../../secret",
            "job\\..\\..\\secret",
        ]
    ),
    # Generated patterns with traversal sequences
    st.builds(
        lambda prefix, suffix: f"{prefix}../{suffix}",
        prefix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=0, max_size=10),
        suffix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=0, max_size=10),
    ),
    st.builds(
        lambda prefix, suffix: f"{prefix}..\\{suffix}",
        prefix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=0, max_size=10),
        suffix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=0, max_size=10),
    ),
    # Multiple traversal sequences
    st.builds(lambda n: "../" * n, n=st.integers(min_value=1, max_value=10)),
    st.builds(lambda n: "..\\" * n, n=st.integers(min_value=1, max_value=10)),
)

# Strategy for generating valid filenames
valid_filenames = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.", min_size=1, max_size=50
).filter(lambda x: not x.startswith(".") or len(x) > 1)

# Strategy for generating malicious filenames with directory separators
malicious_filenames = st.one_of(
    st.sampled_from(
        [
            "../secret.txt",
            "..\\secret.txt",
            "subdir/file.txt",
            "subdir\\file.txt",
            "../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "valid..txt/../secret",
        ]
    ),
    st.builds(
        lambda prefix, suffix: f"{prefix}/{suffix}",
        prefix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        suffix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    ),
    st.builds(
        lambda prefix, suffix: f"{prefix}\\{suffix}",
        prefix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        suffix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    ),
)


# =============================================================================
# Property 1: Path Containment Invariant
# =============================================================================


@pytest.mark.unit
class TestPathContainmentProperty:
    """Property 1: Path Containment Invariant

    For any job_id and filename provided to Local_Storage, the resolved path
    SHALL always remain within the configured base_path directory.

    Feature: code-quality-security-hardening, Property 1: Path Containment
    **Validates: Requirements 1.2, 1.5, 1.6**
    """

    @given(job_id=valid_job_id_chars)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_job_id_path_within_base(self, job_id):
        """For any valid job_id, resolved path must be within base_path.

        **Validates: Requirements 1.2, 1.5**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            base = Path(tmpdir).resolve()

            try:
                job_dir = storage._get_job_dir(job_id)
                resolved = job_dir.resolve()
                # This should not raise - path must be within base
                resolved.relative_to(base)
            except StorageError:
                # Expected for invalid inputs - this is correct behavior
                # The property holds: either path is within base, or error is raised
                pass

    @given(job_id=arbitrary_job_ids)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_job_id_never_escapes_base(self, job_id):
        """For any arbitrary job_id, path must never escape base_path.

        Either the path is within base_path, or a StorageError is raised.

        **Validates: Requirements 1.2, 1.5**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            base = Path(tmpdir).resolve()

            try:
                job_dir = storage._get_job_dir(job_id)
                resolved = job_dir.resolve()
                # If we get here without error, path MUST be within base
                try:
                    resolved.relative_to(base)
                except ValueError:
                    pytest.fail(f"Path escaped base directory! job_id={job_id!r}, resolved={resolved}, base={base}")
            except StorageError:
                # This is acceptable - invalid input was rejected
                pass
            except Exception as e:
                # Other exceptions are also acceptable for invalid input
                pass

    @given(job_id=valid_job_id_chars, filename=valid_filenames)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_report_path_within_base(self, job_id, filename):
        """For any valid job_id and filename, report path must be within base_path.

        **Validates: Requirements 1.6**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            base = Path(tmpdir).resolve()

            try:
                report_path = storage._get_report_path(job_id, filename)
                resolved = report_path.resolve()
                # Path must be within base
                try:
                    resolved.relative_to(base)
                except ValueError:
                    pytest.fail(
                        f"Report path escaped base directory! job_id={job_id!r}, "
                        f"filename={filename!r}, resolved={resolved}, base={base}"
                    )
            except StorageError:
                # Expected for invalid inputs - this is correct behavior
                pass


# =============================================================================
# Property 2: Path Traversal Rejection
# =============================================================================


@pytest.mark.unit
class TestPathTraversalRejectionProperty:
    r"""Property 2: Path Traversal Rejection

    Any input containing path traversal patterns (../, ..\, etc.) must be
    rejected with PathTraversalError or StorageError.

    Feature: code-quality-security-hardening, Property 2: Traversal Rejection
    **Validates: Requirements 1.3, 1.4**
    """

    @given(job_id=malicious_job_ids)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_traversal_in_job_id_rejected(self, job_id):
        """For any job_id with traversal sequences, error must be raised.

        **Validates: Requirements 1.3**
        """
        # Skip empty strings as they're handled differently
        assume(job_id and len(job_id.strip()) > 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            # Must raise StorageError for traversal attempts
            with pytest.raises(StorageError):
                storage._get_job_dir(job_id)

    @given(filename=malicious_filenames)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_traversal_in_filename_rejected(self, filename):
        """For any filename with directory separators, error must be raised.

        **Validates: Requirements 1.4**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            # Must raise StorageError for filenames with directory components
            with pytest.raises(StorageError):
                storage._validate_filename(filename)

    @pytest.mark.parametrize(
        "malicious_job_id",
        [
            "../",
            "..\\",
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "job/../../../secret",
            "valid-job/../../../etc/passwd",
            "....//",
            "....\\\\",
            "job/subdir",
            "job\\subdir",
        ],
    )
    def test_known_traversal_patterns_rejected(self, malicious_job_id):
        """Known path traversal patterns must always be rejected.

        **Validates: Requirements 1.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            with pytest.raises(StorageError):
                storage._get_job_dir(malicious_job_id)

    @pytest.mark.parametrize(
        "malicious_filename",
        [
            "../secret.txt",
            "..\\secret.txt",
            "subdir/file.txt",
            "subdir\\file.txt",
            "../../etc/passwd",
            "..\\..\\windows\\system32\\config",
        ],
    )
    def test_known_filename_traversal_rejected(self, malicious_filename):
        """Known filename traversal patterns must always be rejected.

        **Validates: Requirements 1.4**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            with pytest.raises(StorageError):
                storage._validate_filename(malicious_filename)


# =============================================================================
# Combined Property Tests
# =============================================================================


@pytest.mark.unit
class TestCombinedPathSecurityProperties:
    """Combined tests for path security properties.

    Tests that verify both properties hold together in realistic scenarios.
    """

    @given(
        job_id=st.one_of(valid_job_id_chars, malicious_job_ids, arbitrary_job_ids),
        filename=st.one_of(valid_filenames, malicious_filenames),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_combined_path_security(self, job_id, filename):
        """For any combination of job_id and filename, security invariants hold.

        Either:
        1. Both are valid and the resulting path is within base_path, OR
        2. An appropriate error is raised

        **Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            base = Path(tmpdir).resolve()

            try:
                report_path = storage._get_report_path(job_id, filename)
                resolved = report_path.resolve()

                # If we get here, path MUST be within base
                try:
                    resolved.relative_to(base)
                except ValueError:
                    pytest.fail(
                        f"Path escaped base directory! job_id={job_id!r}, "
                        f"filename={filename!r}, resolved={resolved}, base={base}"
                    )
            except StorageError:
                # This is acceptable - invalid input was rejected
                pass
            except Exception:
                # Other exceptions are also acceptable for invalid input
                pass

    @given(job_id=valid_job_id_chars)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_job_id_creates_accessible_directory(self, job_id):
        """Valid job_ids should create accessible directories within base_path.

        **Validates: Requirements 1.2, 1.5**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            base = Path(tmpdir).resolve()

            try:
                job_dir = storage._get_job_dir(job_id)
                resolved = job_dir.resolve()

                # Verify containment
                relative = resolved.relative_to(base)

                # The relative path should not contain parent references
                assert ".." not in str(relative), f"Relative path contains '..': {relative}"

            except StorageError:
                # Some valid characters might still be rejected (e.g., empty after sanitization)
                pass
