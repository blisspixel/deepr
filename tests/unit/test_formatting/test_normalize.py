"""Unit tests for the Markdown normalization module.

Tests the normalize_markdown function for proper handling of
line breaks, headers, lists, and emphasis formatting.
"""

import pytest

from deepr.formatting.normalize import normalize_markdown


class TestNormalizeMarkdownBasic:
    """Test basic normalization functionality."""

    def test_empty_string(self):
        """Test normalizing empty string."""
        result = normalize_markdown("")
        assert result == ""

    def test_none_input(self):
        """Test normalizing None input."""
        result = normalize_markdown(None)
        assert result == ""

    def test_simple_text(self):
        """Test normalizing simple text."""
        result = normalize_markdown("Hello world")
        assert result == "Hello world"

    def test_preserves_content(self):
        """Test that content is preserved."""
        text = "This is a test paragraph with some content."
        result = normalize_markdown(text)
        assert "This is a test paragraph" in result


class TestNormalizeLineBreaks:
    """Test line break normalization."""

    def test_unix_line_breaks(self):
        """Test Unix-style line breaks are preserved."""
        text = "Line 1\nLine 2\nLine 3"
        result = normalize_markdown(text)
        assert "Line 1\nLine 2\nLine 3" in result

    def test_windows_line_breaks(self):
        """Test Windows-style line breaks are converted."""
        text = "Line 1\r\nLine 2\r\nLine 3"
        result = normalize_markdown(text)
        assert "\r\n" not in result
        assert "Line 1\nLine 2\nLine 3" in result

    def test_old_mac_line_breaks(self):
        """Test old Mac-style line breaks are converted."""
        text = "Line 1\rLine 2\rLine 3"
        result = normalize_markdown(text)
        assert "\r" not in result

    def test_excessive_blank_lines(self):
        """Test excessive blank lines are collapsed."""
        text = "Paragraph 1\n\n\n\n\nParagraph 2"
        result = normalize_markdown(text)
        assert "\n\n\n" not in result
        assert "Paragraph 1\n\nParagraph 2" in result

    def test_trailing_spaces_removed(self):
        """Test trailing spaces are removed from lines."""
        text = "Line with trailing spaces   \nAnother line  "
        result = normalize_markdown(text)
        assert "   \n" not in result
        assert "  " not in result or result.endswith("line")


class TestNormalizeHeaders:
    """Test header normalization."""

    def test_h1_header(self):
        """Test H1 header normalization."""
        text = "#Header"
        result = normalize_markdown(text)
        assert result == "# Header"

    def test_h2_header(self):
        """Test H2 header normalization."""
        text = "##Header"
        result = normalize_markdown(text)
        assert result == "## Header"

    def test_h3_header(self):
        """Test H3 header normalization."""
        text = "###Header"
        result = normalize_markdown(text)
        assert result == "### Header"

    def test_h6_header(self):
        """Test H6 header normalization."""
        text = "######Header"
        result = normalize_markdown(text)
        assert result == "###### Header"

    def test_header_with_leading_space(self):
        """Test header with leading whitespace."""
        text = "  # Header"
        result = normalize_markdown(text)
        assert result == "# Header"

    def test_header_with_extra_spaces(self):
        """Test header with extra spaces after hash."""
        text = "#   Header"
        result = normalize_markdown(text)
        assert result == "# Header"

    def test_header_already_normalized(self):
        """Test already normalized header."""
        text = "# Header"
        result = normalize_markdown(text)
        assert result == "# Header"


class TestNormalizeLists:
    """Test list normalization."""

    def test_dash_list(self):
        """Test dash list items."""
        text = "-  Item 1\n-  Item 2"
        result = normalize_markdown(text)
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_plus_list(self):
        """Test plus list items."""
        text = "+  Item 1\n+  Item 2"
        result = normalize_markdown(text)
        assert "+ Item 1" in result
        assert "+ Item 2" in result

    def test_asterisk_list(self):
        """Test asterisk list items."""
        text = "*  Item 1\n*  Item 2"
        result = normalize_markdown(text)
        assert "* Item 1" in result
        assert "* Item 2" in result

    def test_list_with_leading_space(self):
        """Test list with leading whitespace."""
        text = "  - Item"
        result = normalize_markdown(text)
        assert "- Item" in result

    def test_nested_list(self):
        """Test nested list items."""
        text = "- Item 1\n  - Nested item"
        result = normalize_markdown(text)
        assert "- Item 1" in result
        assert "- Nested item" in result


class TestNormalizeEmphasis:
    """Test emphasis (bold/italic) normalization."""

    def test_underscore_italic_to_asterisk(self):
        """Test underscore italic converted to asterisk."""
        text = "This is _italic_ text"
        result = normalize_markdown(text)
        assert "*italic*" in result

    def test_double_underscore_bold_to_asterisk(self):
        """Test double underscore bold converted to asterisk."""
        text = "This is __bold__ text"
        result = normalize_markdown(text)
        assert "**bold**" in result

    def test_asterisk_italic_preserved(self):
        """Test asterisk italic is preserved."""
        text = "This is *italic* text"
        result = normalize_markdown(text)
        assert "*italic*" in result

    def test_asterisk_bold_preserved(self):
        """Test asterisk bold is preserved."""
        text = "This is **bold** text"
        result = normalize_markdown(text)
        assert "**bold**" in result

    def test_multiple_emphasis(self):
        """Test multiple emphasis in same line."""
        text = "This has _italic_ and __bold__ text"
        result = normalize_markdown(text)
        assert "*italic*" in result
        assert "**bold**" in result


class TestNormalizeComplex:
    """Test complex markdown normalization."""

    def test_full_document(self):
        """Test normalizing a full markdown document."""
        text = """#Title

This is a paragraph with _italic_ and __bold__ text.

##Section 1

-  Item 1
-  Item 2

###Subsection

More content here."""
        
        result = normalize_markdown(text)
        
        assert "# Title" in result
        assert "## Section 1" in result
        assert "### Subsection" in result
        assert "- Item 1" in result
        assert "*italic*" in result
        assert "**bold**" in result

    def test_code_blocks_preserved(self):
        """Test that code content is preserved."""
        text = "```python\ndef hello():\n    print('Hello')\n```"
        result = normalize_markdown(text)
        assert "def hello():" in result
        assert "print('Hello')" in result

    def test_links_preserved(self):
        """Test that links are preserved."""
        text = "Check out [this link](https://example.com)"
        result = normalize_markdown(text)
        assert "[this link](https://example.com)" in result

    def test_images_preserved(self):
        """Test that images are preserved."""
        text = "![Alt text](image.png)"
        result = normalize_markdown(text)
        assert "![Alt text](image.png)" in result


class TestNormalizeEdgeCases:
    """Test edge cases in normalization."""

    def test_only_whitespace(self):
        """Test string with only whitespace."""
        text = "   \n\n   \n"
        result = normalize_markdown(text)
        # Should collapse to minimal whitespace
        assert result.strip() == ""

    def test_single_hash(self):
        """Test single hash without text."""
        text = "#"
        result = normalize_markdown(text)
        assert "#" in result

    def test_hash_in_middle_of_line(self):
        """Test hash in middle of line (not a header)."""
        text = "This is a C# programming language"
        result = normalize_markdown(text)
        assert "C#" in result

    def test_underscore_in_variable_name(self):
        """Test underscore in variable names."""
        text = "Use the variable_name in your code"
        result = normalize_markdown(text)
        # Should not convert underscores in variable names
        assert "variable" in result

    def test_multiple_underscores(self):
        """Test multiple underscores."""
        text = "This has __multiple__ __bold__ words"
        result = normalize_markdown(text)
        assert "**multiple**" in result
        assert "**bold**" in result

    def test_unicode_content(self):
        """Test unicode content is preserved."""
        text = "# 日本語タイトル\n\nこれは日本語のテキストです。"
        result = normalize_markdown(text)
        assert "日本語タイトル" in result
        assert "日本語のテキスト" in result

    def test_emoji_content(self):
        """Test emoji content is preserved."""
        text = "# Hello 👋\n\nThis is a test 🎉"
        result = normalize_markdown(text)
        assert "👋" in result
        assert "🎉" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
