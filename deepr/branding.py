"""
ASCII art branding for Deepr CLI applications.

DEPRECATED: This module is deprecated. Use deepr.cli.colors instead for modern CLI output.

The functions in this module use legacy ASCII art and separators that don't match
modern 2026 CLI design standards. New code should use:
- deepr.cli.colors.print_header() instead of print_section_header()
- deepr.cli.colors.print_success/error/warning() instead of CHECK/CROSS symbols
- deepr.cli.colors.get_symbol() for Unicode symbols with ASCII fallback
"""

import warnings

DEEPR_BANNER = r"""
===============================================================================

    ########   ##########  ##########  ########      #######
    ##    ##   ##          ##          ##     ##     ##    ##
    ##     ##  ########    ########    ########      ########
    ##    ##   ##          ##          ##            ##    ##
    ########   ##########  ##########  ##            ##     ##

               Knowledge Is Power, Automate It

===============================================================================
"""

DEEPR_BANNER_MINIMAL = r"""
-----------------------------------------------------------------------
  ########   ##########  ##########  ########      #######
  ##    ##   ##          ##          ##     ##     ##    ##
  ##     ##  ########    ########    ########      ########
  ##    ##   ##          ##          ##            ##    ##
  ########   ##########  ##########  ##            ##     ##

           Knowledge Is Power, Automate It
-----------------------------------------------------------------------
"""

DEEPR_SIMPLE = r"""
----------------------------------------
  DEEPR
  Deep Research Automation
  Knowledge Is Power, Automate It
----------------------------------------
"""

MANAGER_BANNER = r"""
===============================================================================

    ########   ##########  ##########  ########      #######
    ##    ##   ##          ##          ##     ##     ##    ##
    ##     ##  ########    ########    ########      ########
    ##    ##   ##          ##          ##            ##    ##
    ########   ##########  ##########  ##            ##     ##

                         Job Manager
               Manage, Monitor, and Control Jobs

===============================================================================
"""

SETUP_BANNER = r"""
===============================================================================

    ########   ##########  ##########  ########      #######
    ##    ##   ##          ##          ##     ##     ##    ##
    ##     ##  ########    ########    ########      ########
    ##    ##   ##          ##          ##            ##    ##
    ########   ##########  ##########  ##            ##     ##

                      Environment Setup
            Initializing your Deepr development environment

===============================================================================
"""


def print_banner(banner_type: str = "main"):
    """
    Print ASCII banner for CLI applications.
    
    DEPRECATED: ASCII banners are deprecated. Modern CLIs use minimal headers.
    Use deepr.cli.colors.print_header() instead.

    Args:
        banner_type: Type of banner to print (main, minimal, simple, manager, setup)
    """
    warnings.warn(
        "print_banner() is deprecated. Use deepr.cli.colors.print_header() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    banners = {
        "main": DEEPR_BANNER,
        "minimal": DEEPR_BANNER_MINIMAL,
        "simple": DEEPR_SIMPLE,
        "manager": MANAGER_BANNER,
        "setup": SETUP_BANNER,
    }

    print(banners.get(banner_type, DEEPR_BANNER))


def print_separator(width: int = 70, char: str = "="):
    """Print a separator line.
    
    DEPRECATED: Separator lines are deprecated. Modern CLIs use whitespace for hierarchy.
    """
    warnings.warn(
        "print_separator() is deprecated. Use whitespace or deepr.cli.colors.print_header() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    print(char * width)


def print_section_header(title: str, width: int = 70):
    """Print a formatted section header.
    
    DEPRECATED: Use deepr.cli.colors.print_header() instead.
    """
    warnings.warn(
        "print_section_header() is deprecated. Use deepr.cli.colors.print_header() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    print()
    print(f"{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")
    print()


# Cross-platform symbols - DEPRECATED, use deepr.cli.colors.get_symbol() instead
CHECK = "[OK]"
CROSS = "[X]"
ARROW = "=>"

try:
    # Try to use Unicode symbols on systems that support them
    import sys
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('cp1252', 'ascii'):
        CHECK = "✓"
        CROSS = "✗"
        ARROW = "→"
except Exception:
    pass
