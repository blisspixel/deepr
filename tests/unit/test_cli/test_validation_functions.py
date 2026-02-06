"""Tests for CLI validation functions.

Tests cover:
- validate_upload_files
- validate_prompt
- validate_expert_name
- validate_budget
- confirm_high_cost_operation
"""

from unittest.mock import patch

import click
import pytest

from deepr.cli.validation import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    MAX_FILE_SIZE_MB,
    confirm_high_cost_operation,
    validate_budget,
    validate_expert_name,
    validate_prompt,
    validate_upload_files,
)


class TestValidateUploadFiles:
    """Tests for validate_upload_files function."""

    def test_empty_tuple(self):
        """Empty file tuple should return empty list."""
        result = validate_upload_files(())
        assert result == []

    def test_valid_txt_file(self, tmp_path):
        """Valid txt file should be accepted."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = validate_upload_files((str(test_file),))

        assert len(result) == 1
        assert result[0].name == "test.txt"

    def test_valid_pdf_file(self, tmp_path):
        """Valid pdf file should be accepted."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        result = validate_upload_files((str(test_file),))

        assert len(result) == 1
        assert result[0].suffix == ".pdf"

    def test_multiple_valid_files(self, tmp_path):
        """Multiple valid files should all be accepted."""
        file1 = tmp_path / "test1.txt"
        file1.write_text("content 1")
        file2 = tmp_path / "test2.md"
        file2.write_text("content 2")

        result = validate_upload_files((str(file1), str(file2)))

        assert len(result) == 2

    def test_file_not_found_raises_error(self, tmp_path):
        """Non-existent file should raise UsageError."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_upload_files((str(tmp_path / "nonexistent.txt"),))

        assert "not found" in str(exc_info.value).lower()

    def test_invalid_extension_raises_error(self, tmp_path):
        """File with invalid extension should raise UsageError."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"fake exe")

        with pytest.raises(click.UsageError) as exc_info:
            validate_upload_files((str(test_file),))

        assert "validation failed" in str(exc_info.value).lower()

    def test_custom_allowed_extensions(self, tmp_path):
        """Custom allowed extensions should be respected."""
        test_file = tmp_path / "test.xyz"
        test_file.write_text("content")

        result = validate_upload_files((str(test_file),), allowed_extensions=[".xyz"])

        assert len(result) == 1


class TestValidatePrompt:
    """Tests for validate_prompt function."""

    def test_valid_prompt(self):
        """Valid prompt should be returned unchanged."""
        prompt = "This is a valid prompt"
        result = validate_prompt(prompt)
        assert result == prompt

    def test_empty_prompt(self):
        """Empty prompt should be accepted."""
        result = validate_prompt("")
        assert result == ""

    def test_max_length_prompt(self):
        """Prompt at max length should be accepted."""
        prompt = "a" * 1000
        result = validate_prompt(prompt, max_length=1000)
        assert result == prompt

    def test_over_max_length_raises_error(self):
        """Prompt over max length should raise UsageError."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_prompt("a" * 101, max_length=100)

        assert "validation failed" in str(exc_info.value).lower()

    def test_custom_field_name_in_error(self):
        """Custom field name should appear in error."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_prompt("a" * 101, max_length=100, field_name="query")

        assert "query" in str(exc_info.value).lower()


class TestValidateExpertName:
    """Tests for validate_expert_name function."""

    def test_valid_name(self):
        """Valid name should be returned unchanged."""
        name = "My Expert"
        result = validate_expert_name(name)
        assert result == name

    def test_alphanumeric_name(self):
        """Alphanumeric name should be accepted."""
        result = validate_expert_name("Expert123")
        assert result == "Expert123"

    def test_name_with_hyphen(self):
        """Name with hyphen should be accepted."""
        result = validate_expert_name("my-expert")
        assert result == "my-expert"

    def test_name_with_underscore(self):
        """Name with underscore should be accepted."""
        result = validate_expert_name("my_expert")
        assert result == "my_expert"

    def test_empty_name_raises_error(self):
        """Empty name should raise UsageError."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_expert_name("")

        assert "cannot be empty" in str(exc_info.value).lower()

    def test_whitespace_only_raises_error(self):
        """Whitespace-only name should raise UsageError."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_expert_name("   ")

        assert "cannot be empty" in str(exc_info.value).lower()

    def test_too_long_name_raises_error(self):
        """Name over 100 chars should raise UsageError."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_expert_name("a" * 101)

        assert "too long" in str(exc_info.value).lower()

    def test_special_characters_raises_error(self):
        """Name with special characters should raise UsageError."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_expert_name("Expert@Test!")

        assert "only contain" in str(exc_info.value).lower()


class TestValidateBudget:
    """Tests for validate_budget function."""

    def test_valid_budget(self):
        """Valid budget should be returned unchanged."""
        result = validate_budget(5.0)
        assert result == 5.0

    def test_zero_budget(self):
        """Zero budget should be accepted."""
        result = validate_budget(0.0)
        assert result == 0.0

    def test_negative_budget_raises_error(self):
        """Negative budget should raise UsageError."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_budget(-1.0)

        assert "cannot be less than" in str(exc_info.value).lower()

    def test_below_min_budget_raises_error(self):
        """Budget below minimum should raise UsageError."""
        with pytest.raises(click.UsageError) as exc_info:
            validate_budget(0.5, min_budget=1.0)

        assert "cannot be less than" in str(exc_info.value).lower()

    @patch("deepr.cli.validation.click.echo")
    def test_warn_threshold_shows_warning(self, mock_echo):
        """Budget above warn threshold should show warning."""
        result = validate_budget(15.0, warn_threshold=10.0, confirm_threshold=25.0)

        assert result == 15.0
        mock_echo.assert_called()
        call_args = str(mock_echo.call_args)
        assert "WARN" in call_args

    @patch("deepr.cli.validation.click.echo")
    @patch("deepr.cli.validation.click.confirm", return_value=True)
    def test_confirm_threshold_requires_confirmation(self, mock_confirm, mock_echo):
        """Budget above confirm threshold should require confirmation."""
        result = validate_budget(30.0, confirm_threshold=25.0)

        assert result == 30.0
        mock_confirm.assert_called_once()

    @patch("deepr.cli.validation.click.echo")
    @patch("deepr.cli.validation.click.confirm", return_value=False)
    def test_confirm_declined_raises_abort(self, mock_confirm, mock_echo):
        """Declining confirmation should raise Abort."""
        with pytest.raises(click.Abort):
            validate_budget(30.0, confirm_threshold=25.0)


class TestConfirmHighCostOperation:
    """Tests for confirm_high_cost_operation function."""

    def test_below_threshold_returns_true(self):
        """Cost below threshold should return True without prompting."""
        result = confirm_high_cost_operation(2.0, threshold=5.0)
        assert result is True

    def test_skip_confirm_returns_true(self):
        """skip_confirm=True should return True without prompting."""
        result = confirm_high_cost_operation(100.0, skip_confirm=True)
        assert result is True

    @patch("deepr.cli.validation.click.echo")
    @patch("deepr.cli.validation.click.confirm", return_value=True)
    def test_above_threshold_confirms(self, mock_confirm, mock_echo):
        """Cost above threshold should prompt and return True on confirmation."""
        result = confirm_high_cost_operation(10.0, threshold=5.0)

        assert result is True
        mock_confirm.assert_called_once()
        # Should show cost warning
        assert any("10.00" in str(call) for call in mock_echo.call_args_list)

    @patch("deepr.cli.validation.click.echo")
    @patch("deepr.cli.validation.click.confirm", return_value=False)
    def test_declined_raises_abort(self, mock_confirm, mock_echo):
        """Declining confirmation should raise Abort."""
        with pytest.raises(click.Abort):
            confirm_high_cost_operation(10.0, threshold=5.0)


class TestModuleConstants:
    """Tests for module constants."""

    def test_allowed_extensions_includes_common_types(self):
        """ALLOWED_DOCUMENT_EXTENSIONS should include common file types."""
        assert ".pdf" in ALLOWED_DOCUMENT_EXTENSIONS
        assert ".txt" in ALLOWED_DOCUMENT_EXTENSIONS
        assert ".md" in ALLOWED_DOCUMENT_EXTENSIONS
        assert ".py" in ALLOWED_DOCUMENT_EXTENSIONS
        assert ".json" in ALLOWED_DOCUMENT_EXTENSIONS

    def test_max_file_size_reasonable(self):
        """MAX_FILE_SIZE_MB should be reasonable (e.g., 100MB)."""
        assert MAX_FILE_SIZE_MB == 100
