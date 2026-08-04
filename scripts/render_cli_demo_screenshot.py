"""Render a fictional CLI demo screenshot for README polish.

Demo data only. No live account, no real research content.
"""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - developer tooling only
    raise SystemExit(
        "Pillow is required to render README CLI screenshots. "
        "Install with: uv pip install pillow"
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "cli-demo.png"

W, H = 1320, 860
TITLEBAR_H = 36
PAD_X, PAD_Y = 22, 14
LINE_H = 19

BG = (18, 18, 20)
TITLE_BG = (32, 32, 36)
BORDER = (48, 48, 54)
FG = (220, 220, 224)
DIM = (140, 140, 148)
CYAN = (100, 200, 220)
GREEN = (110, 200, 140)
YELLOW = (220, 190, 100)
RED = (230, 120, 120)
BLUE = (140, 170, 240)
MUTED = (100, 100, 110)


def _font(name: str, size: int) -> ImageFont.ImageFont:
    path = Path("C:/Windows/Fonts") / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([8, 8, W - 9, H - 9], radius=14, outline=BORDER, width=2, fill=BG)
    draw.rounded_rectangle([8, 8, W - 9, 8 + TITLEBAR_H], radius=14, fill=TITLE_BG)
    draw.rectangle([8, 8 + TITLEBAR_H - 14, W - 9, 8 + TITLEBAR_H], fill=TITLE_BG)

    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        x = 28 + i * 20
        draw.ellipse([x, 18, x + 12, 30], fill=color)

    font_title = _font("segoeui.ttf", 14)
    font = _font("consola.ttf", 14)
    font_bold = _font("consolab.ttf", 14)

    title = "deepr  -  demo session (fictional)"
    draw.text((W // 2 - 120, 14), title, fill=DIM, font=font_title)

    lines: list[tuple[str, tuple[int, int, int], bool]] = [
        ("PS C:\\demo\\deepr> deepr doctor --skip-connectivity", FG, False),
        ("", FG, False),
        ("  MCP", CYAN, True),
        ("  OK MCP offline conformance: ok (6 checks; modern 2026-07-28)", GREEN, False),
        ("      Run: deepr mcp conformance --json", DIM, False),
        ("  Spend", CYAN, True),
        ("  OK Monthly spend vs budget: $0.00 of $5.00", GREEN, False),
        ("  OK Paid artifacts: no unexplained spend", GREEN, False),
        ("  Summary: 15/19 checks passed (advisory only)", DIM, False),
        ("", FG, False),
        ("PS C:\\demo\\deepr> deepr capacity", FG, False),
        ("", FG, False),
        ("  Class            Status        Notes", DIM, False),
        ("  --------------   -----------   -----------------------------------------", MUTED, False),
        ("  local ollama     executable    endpoint owned; $0 model margin", GREEN, False),
        ("  plan quota       visible       claude code after overage-off proof", YELLOW, False),
        ("  metered api      blocked       account-control verifier not installed", RED, False),
        ("", FG, False),
        (
            'PS C:\\demo\\deepr> deepr expert consult "What should we decide next?" '
            '--expert "Aurora Harbor Pilotage" --local',
            FG,
            False,
        ),
        ("", FG, False),
        ("  Expert   Aurora Harbor Pilotage  (demo)", CYAN, True),
        ("  Mode     local ollama / $0 margin", DIM, False),
        ("  Budget   parent ceiling $0.00 (owned local)", DIM, False),
        ("", FG, False),
        ("  Position", BLUE, True),
        ("  Prioritize channel-depth survey before expanding night traffic.", FG, False),
        ("  Evidence favors staged pilot rotations over permanent second boat.", FG, False),
        ("", FG, False),
        ("  Beliefs (sample)", BLUE, True),
        ("  +  Tide windows under 0.4 m residual reduce grounding risk   conf 0.78", GREEN, False),
        ("  +  Dual-pilot nights cut delay variance in fog               conf 0.71", GREEN, False),
        ("  ~  Second launch ROI depends on peak-season utilization      conf 0.44", YELLOW, False),
        ("", FG, False),
        ("  Gaps", BLUE, True),
        ("  -  Missing 12-month fog delay ledger for eastern approach", YELLOW, False),
        ("  -  No calibrated cost model for standby pilot hours", YELLOW, False),
        ("", FG, False),
        ("  Uncertainty", BLUE, True),
        ("  Would revise if peak-season utilization exceeds 62% for two seasons.", DIM, False),
        ("", FG, False),
        ("PS C:\\demo\\deepr> deepr costs doctor --json", FG, False),
        (
            '  {"matched_spend_usd": 0.0, "disposed_spend_usd": 0.0, "unexplained_spend_usd": 0.0}',
            DIM,
            False,
        ),
        ("", FG, False),
        ("PS C:\\demo\\deepr> _", FG, False),
    ]

    y = 8 + TITLEBAR_H + PAD_Y
    for text, color, bold in lines:
        f = font_bold if bold else font
        # Soft wrap long lines
        if len(text) > 108:
            chunk = text
            while chunk:
                piece = chunk[:108]
                draw.text((PAD_X + 8, y), piece, fill=color, font=f)
                y += LINE_H
                chunk = chunk[108:]
                if chunk:
                    chunk = "    " + chunk
            continue
        draw.text((PAD_X + 8, y), text, fill=color, font=f)
        y += LINE_H
        if y > H - 28:
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
