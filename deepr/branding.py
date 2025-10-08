"""
ASCII art branding for Deepr CLI applications.

Provides consistent visual branding across all CLI entry points.
"""

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

    Args:
        banner_type: Type of banner to print (main, minimal, simple, manager, setup)
    """
    banners = {
        "main": DEEPR_BANNER,
        "minimal": DEEPR_BANNER_MINIMAL,
        "simple": DEEPR_SIMPLE,
        "manager": MANAGER_BANNER,
        "setup": SETUP_BANNER,
    }

    print(banners.get(banner_type, DEEPR_BANNER))


def print_separator(width: int = 70, char: str = "="):
    """Print a separator line."""
    print(char * width)


def print_section_header(title: str, width: int = 70):
    """Print a formatted section header."""
    print()
    print(f"{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")
    print()


# Cross-platform symbols
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
