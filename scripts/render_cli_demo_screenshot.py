"""Render the README CLI walkthrough from the verified bounded-spend run."""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - developer tooling only
    raise SystemExit(
        "Pillow is required to render README CLI screenshots. Install with: uv pip install pillow"
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

    title = "deepr  -  bounded spend and expert improvement"
    draw.text((W // 2 - 180, 14), title, fill=DIM, font=font_title)

    lines: list[tuple[str, tuple[int, int, int], bool]] = [
        ("PS C:\\GitHub\\deepr> deepr budget allow --amount 2.00 --minutes 60 --provider openai", FG, False),
        ("", FG, False),
        ("  Month exposure    : $0.00", DIM, False),
        ("  Unresolved holds  : 0", DIM, False),
        ("  Requested ceiling : $2.00 for 60 minute(s)", FG, False),
        ("  Type 2.00 to confirm: 2.00", YELLOW, False),
        ("  Granted $2.00. This is one total drawdown, not $2 per call.", GREEN, True),
        ("", FG, False),
        ("PS C:\\GitHub\\deepr> deepr costs show", FG, False),
        ("", FG, False),
        ("  API Grant Costs", CYAN, True),
        ("  Attended paid API grant", FG, True),
        ("  Settled since grant: $0.01", FG, False),
        ("  Active holds: $0.00", GREEN, False),
        ("  Unresolved post-dispatch holds: 0 ($0.00)", GREEN, False),
        ("  Total drawdown: $0.01 / $2.00", BLUE, True),
        ("  Remaining: $1.99", GREEN, True),
        ("  Local and verified prepaid-plan work records $0 and does not draw down the grant.", DIM, False),
        ("", FG, False),
        (
            'PS C:\\GitHub\\deepr> deepr expert absorb "Knowledge System Evaluation" '
            '--file docs/design/expert-purpose-and-value-loop.md --api --budget 0.30 -y',
            FG,
            False,
        ),
        ("", FG, False),
        ("  Run ceiling       $0.30", DIM, False),
        ("  Provider / model  OpenAI / gpt-5-mini", DIM, False),
        ("  Paid calls         1 extraction + 5 short semantic checks", DIM, False),
        ("  Exact settled      $0.011031", GREEN, True),
        ("  Durable holds      0 active, 0 unresolved", GREEN, False),
        ("", FG, False),
        ("  Knowledge System Evaluation", BLUE, True),
        ("  Before             0 canonical claims / foundation", RED, False),
        ("  After              20 canonical claims / learning", GREEN, True),
        ("  Average confidence 0.942", GREEN, False),
        ("", FG, False),
        ("PS C:\\GitHub\\deepr> deepr budget revoke", FG, False),
        ("", FG, False),
        ("  Grant revoked. Paid dispatch is frozen again.", GREEN, True),
        ("", FG, False),
        ("PS C:\\GitHub\\deepr> _", FG, False),
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
