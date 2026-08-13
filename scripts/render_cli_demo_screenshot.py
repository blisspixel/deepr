"""Render the README CLI walkthrough for a cumulative spend wallet."""

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
BLUE = (140, 170, 240)


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

    title = "deepr  -  prepaid-style local wallet and hard job ceiling"
    draw.text((W // 2 - 180, 14), title, fill=DIM, font=font_title)

    lines: list[tuple[str, tuple[int, int, int], bool]] = [
        (
            'PS C:\\GitHub\\deepr> deepr budget credits add --amount 200.00 --reason "Bound this API campaign"',
            FG,
            False,
        ),
        ("", FG, False),
        ("  All-time settled  : $0.00", DIM, False),
        ("  Active holds      : $0.00", DIM, False),
        ("  Credit addition   : $200.00", FG, False),
        ("  Resulting ceiling : $200.00", FG, False),
        ("", FG, False),
        ("  This is local Deepr authorization. It does not buy or verify provider credits.", YELLOW, False),
        ("  Provider prepaid credits or a hard stop with overage disabled must also be verified.", YELLOW, False),
        ("  An open postpaid account remains blocked even with this Deepr wallet.", YELLOW, True),
        ("  Type 200.00 to confirm: 200.00", YELLOW, False),
        ("  Added $200.00; wallet now authorizes $200.00 total.", GREEN, True),
        ("  Available after active holds: $200.00", GREEN, False),
        ("  Automatic refill: disabled", GREEN, True),
        ("", FG, False),
        ("PS C:\\GitHub\\deepr> deepr budget status", FG, False),
        ("", FG, False),
        ("  Mode: Wallet funded; provider hard boundary required", CYAN, True),
        ("  Wallet drawdown: $0.00 / $200.00 (0%)", BLUE, True),
        ("  Wallet available: $200.00", GREEN, True),
        ("  Configured independent monthly ceiling: $5.00", FG, True),
        ("  Monthly exposure with holds: $0.00", FG, False),
        ("  Monthly headroom: $5.00", GREEN, False),
        ("  Provider hard boundary: not verified; paid API remains blocked", YELLOW, True),
        ("", FG, False),
        ("PS C:\\GitHub\\deepr> deepr costs show", FG, False),
        ("", FG, False),
        ("  Deepr metered-spend wallet", CYAN, True),
        ("  Authorized credits: $200.00", FG, False),
        ("  Settled from wallet: $0.00", FG, False),
        ("  Active / unresolved holds: $0.00 / 0", GREEN, False),
        ("  Wallet available: $200.00", GREEN, True),
        ("  Effective monthly exposure: $0.00 / $5.00", FG, False),
        ("  Configured per-job ceiling: $4.00", BLUE, True),
        ("  Maximum new paid call now: $0.00 until provider verification", YELLOW, True),
        ("  Local and verified plan-quota work records $0 and does not draw down this wallet.", DIM, False),
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
