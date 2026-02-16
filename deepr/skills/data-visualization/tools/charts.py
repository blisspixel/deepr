"""ASCII chart generation."""

from __future__ import annotations


def ascii_chart(
    labels: list[str],
    values: list[float],
    title: str | None = None,
    width: int = 40,
    unit: str = "",
) -> dict[str, str]:
    """Create an ASCII bar chart.

    Args:
        labels: Bar labels
        values: Bar values
        title: Chart title
        width: Max bar width in characters
        unit: Unit label after values

    Returns:
        Dictionary with 'chart' key containing the ASCII chart
    """
    if not labels or not values:
        return {"chart": "*No data to chart*"}

    # Ensure equal lengths
    n = min(len(labels), len(values))
    labels = labels[:n]
    values = values[:n]

    max_val = max(abs(v) for v in values) if values else 1
    max_label_len = max(len(str(lbl)) for lbl in labels)

    lines = []
    if title:
        lines.append(title)
        lines.append("=" * (max_label_len + width + 15))

    for label, value in zip(labels, values):
        bar_len = int(abs(value) / max_val * width) if max_val > 0 else 0
        bar = "\u2588" * bar_len
        val_str = f"{value:,.2f}{unit}" if isinstance(value, float) else f"{value}{unit}"
        lines.append(f"{label!s:>{max_label_len}} | {bar} {val_str}")

    return {"chart": "\n".join(lines)}
