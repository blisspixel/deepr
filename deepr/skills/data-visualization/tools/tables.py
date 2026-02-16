"""Markdown table formatting."""

from __future__ import annotations

from typing import Any


def markdown_table(
    headers: list[str],
    rows: list[list[Any]],
    sort_by: int | None = None,
    reverse: bool = False,
    alignments: list[str] | None = None,
) -> dict[str, str]:
    """Format data as a markdown table.

    Args:
        headers: Column headers
        rows: Rows of data
        sort_by: Column index to sort by
        reverse: Sort descending
        alignments: Column alignments (left/center/right)

    Returns:
        Dictionary with 'table' key containing the markdown string
    """
    if not headers or not rows:
        return {"table": "*No data to display*"}

    # Sort if requested
    if sort_by is not None and 0 <= sort_by < len(headers):
        try:
            rows = sorted(rows, key=lambda r: r[sort_by] if sort_by < len(r) else "", reverse=reverse)
        except (TypeError, IndexError):
            pass  # Skip sorting if types are incompatible

    # Convert all values to strings
    str_rows = [[str(cell) for cell in row] for row in rows]

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    # Build alignment separators
    if alignments and len(alignments) == len(headers):
        sep_parts = []
        for i, align in enumerate(alignments):
            w = widths[i]
            if align == "right":
                sep_parts.append("-" * (w - 1) + ":")
            elif align == "center":
                sep_parts.append(":" + "-" * (w - 2) + ":")
            else:
                sep_parts.append("-" * w)
    else:
        sep_parts = ["-" * w for w in widths]

    # Build table
    lines = []
    header_line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line = "| " + " | ".join(sep_parts) + " |"
    lines.append(header_line)
    lines.append(sep_line)

    for row in str_rows:
        padded = []
        for i in range(len(headers)):
            cell = row[i] if i < len(row) else ""
            padded.append(cell.ljust(widths[i]))
        lines.append("| " + " | ".join(padded) + " |")

    return {"table": "\n".join(lines)}
