"""Tests for branding module (deprecated)."""

import warnings
import pytest


class TestBranding:
    """Test branding constants and deprecated functions."""

    def test_banner_constants_exist(self):
        """All banner constants are defined."""
        from deepr.branding import DEEPR_BANNER, DEEPR_BANNER_MINIMAL, DEEPR_SIMPLE, MANAGER_BANNER, SETUP_BANNER
        assert "Knowledge Is Power" in DEEPR_BANNER
        assert "Knowledge Is Power" in DEEPR_BANNER_MINIMAL
        assert "DEEPR" in DEEPR_SIMPLE
        assert "Job Manager" in MANAGER_BANNER
        assert "Environment Setup" in SETUP_BANNER

    def test_print_banner_deprecation_warning(self):
        """print_banner emits DeprecationWarning."""
        from deepr.branding import print_banner
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            print_banner("simple")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

    def test_print_separator_deprecation_warning(self):
        """print_separator emits DeprecationWarning."""
        from deepr.branding import print_separator
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            print_separator()
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_print_section_header_deprecation_warning(self):
        """print_section_header emits DeprecationWarning."""
        from deepr.branding import print_section_header
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            print_section_header("Test")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_symbols_are_strings(self):
        """CHECK, CROSS, ARROW are non-empty strings."""
        from deepr.branding import CHECK, CROSS, ARROW
        assert isinstance(CHECK, str) and len(CHECK) > 0
        assert isinstance(CROSS, str) and len(CROSS) > 0
        assert isinstance(ARROW, str) and len(ARROW) > 0
