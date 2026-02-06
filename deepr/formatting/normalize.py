import logging
import re

logger = logging.getLogger(__name__)


def normalize_markdown(text: str) -> str:
    """
    Normalize the Markdown by ensuring proper line breaks, consistent syntax,
    and standardizing Markdown elements for conversion, while preserving line breaks.
    """
    if not text:
        logger.warning("Input text is empty")
        return ""

    # Normalize line breaks to Unix-style (LF)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    for i, line in enumerate(lines):
        # Strip trailing spaces from each line
        lines[i] = line.rstrip()

        # Normalize headers
        lines[i] = re.sub(r"^\s*(#{1,6})\s*", r"\1 ", lines[i])

        # Ensure proper spacing around list items
        lines[i] = re.sub(r"^\s*([-+*])\s+", r"\1 ", lines[i])

        # --- CORRECTED BOLD/ITALIC LOGIC ---
        # Normalize underscore-based emphasis to asterisk-based for consistency
        # _italic_ -> *italic*
        lines[i] = re.sub(r"(?<!_)_(?!_)(.*?)(?<!_)_(?!_)", r"*\1*", lines[i])
        # __bold__ -> **bold**
        lines[i] = re.sub(r"__([^_]+)__", r"**\1**", lines[i])

    normalized_text = "\n".join(lines)
    # Collapse excessive blank lines to a single blank line
    normalized_text = re.sub(r"\n\s*\n+", "\n\n", normalized_text)

    return normalized_text
