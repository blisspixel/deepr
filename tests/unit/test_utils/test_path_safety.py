"""Tests for path-safety validators in deepr.utils.security.

Covers validate_identifier (slug/uuid path-segment validation) and
safe_path_within (containment-checked path joining).
"""

import pytest

from deepr.utils.security import safe_path_within, validate_identifier


class TestValidateIdentifier:
    """Tests for validate_identifier."""

    @pytest.mark.parametrize(
        "value",
        [
            "my-expert",
            "session_1",
            "report.v2",
            "abc",
            "A1",
            "123e4567-e89b-12d3-a456-426614174000",
        ],
    )
    def test_valid_identifiers_pass(self, value):
        assert validate_identifier(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            "../etc",
            "..",
            ".",
            "a/b",
            "a\\b",
            "/abs",
            "C:\\windows",
            "has space",
            "trailing-",
            "-leading",
            "_underscore_edge",
            "weird!char",
            "emoji-\U0001f600",
        ],
    )
    def test_invalid_identifiers_raise(self, value):
        with pytest.raises(ValueError):
            validate_identifier(value)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            validate_identifier("")

    def test_null_byte_raises(self):
        with pytest.raises(ValueError):
            validate_identifier("ab\x00cd")

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            validate_identifier(123)  # type: ignore[arg-type]

    def test_kind_label_in_message(self):
        with pytest.raises(ValueError, match="job id"):
            validate_identifier("../x", kind="job id")


class TestSafePathWithin:
    """Tests for safe_path_within."""

    def test_simple_join_stays_inside(self, tmp_path):
        result = safe_path_within(tmp_path, "experts", "alice")
        assert result == (tmp_path / "experts" / "alice").resolve()
        assert tmp_path.resolve() in result.parents

    def test_parent_traversal_escapes(self, tmp_path):
        with pytest.raises(ValueError):
            safe_path_within(tmp_path, "..", "etc")

    def test_embedded_traversal_escapes(self, tmp_path):
        with pytest.raises(ValueError):
            safe_path_within(tmp_path, "experts", "..", "..", "secret")

    def test_absolute_segment_escapes(self, tmp_path):
        # An absolute segment replaces the join base under pathlib semantics.
        abs_seg = "C:\\windows" if pytest.importorskip("os").name == "nt" else "/etc"
        with pytest.raises(ValueError):
            safe_path_within(tmp_path, abs_seg, "passwd")

    def test_no_parts_raises(self, tmp_path):
        with pytest.raises(ValueError):
            safe_path_within(tmp_path)

    def test_empty_segment_raises(self, tmp_path):
        with pytest.raises(ValueError):
            safe_path_within(tmp_path, "ok", "")

    def test_traversal_back_into_base_is_allowed(self, tmp_path):
        # Escapes then returns: net result is still inside base, so allowed.
        result = safe_path_within(tmp_path, "a", "..", "b")
        assert result == (tmp_path / "b").resolve()
