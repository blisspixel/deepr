"""Render a fictional web dashboard screenshot for README polish.

Demo data only. No live account, no real research content. Pure PIL mock so
CI and Windows/Linux hosts do not need a browser or Playwright.
"""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - developer tooling only
    raise SystemExit(
        "Pillow is required to render README web screenshots. "
        "Install with: uv pip install pillow"
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "dashboard.png"

W, H = 1280, 800
SIDEBAR_W = 220
BG = (12, 12, 14)
PANEL = (22, 22, 26)
BORDER = (48, 48, 54)
FG = (230, 230, 234)
MUTED = (140, 140, 148)
PRIMARY = (100, 160, 255)
GREEN = (90, 190, 130)
YELLOW = (220, 180, 90)
RED = (230, 120, 120)
WARNING_BG = (50, 40, 20)


def _font(name: str, size: int) -> ImageFont.ImageFont:
    path = Path("C:/Windows/Fonts") / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], **kwargs) -> None:
    draw.rounded_rectangle(box, radius=12, **kwargs)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    title = _font("segoeui.ttf", 20)
    body = _font("segoeui.ttf", 14)
    small = _font("segoeui.ttf", 12)
    mono = _font("consola.ttf", 12)

    # Sidebar
    draw.rectangle([0, 0, SIDEBAR_W, H], fill=(16, 16, 18))
    draw.line([(SIDEBAR_W, 0), (SIDEBAR_W, H)], fill=BORDER)
    draw.text((20, 22), "Deepr", fill=FG, font=title)
    draw.text((20, 48), "demo dashboard", fill=MUTED, font=small)

    nav = [
        ("Overview", True),
        ("Research", False),
        ("Experts", False),
        ("Results", False),
        ("Costs", False),
        ("Settings", False),
    ]
    y = 90
    for label, active in nav:
        if active:
            _rounded(draw, (12, y - 6, SIDEBAR_W - 12, y + 26), fill=(32, 40, 56))
            draw.text((24, y), label, fill=PRIMARY, font=body)
        else:
            draw.text((24, y), label, fill=MUTED, font=body)
        y += 40

    # Main
    mx = SIDEBAR_W + 28
    draw.text((mx, 24), "Overview", fill=FG, font=title)
    draw.text((mx, 52), "Research operations at a glance  ·  demo data", fill=MUTED, font=small)

    # Freeze banner
    _rounded(draw, (mx, 84, W - 28, 140), fill=WARNING_BG, outline=YELLOW)
    draw.text((mx + 16, 96), "Paid API frozen", fill=YELLOW, font=body)
    draw.text(
        (mx + 16, 116),
        "Effective monthly paid ceiling is $0.00. Local and proven plan-quota capacity remain available.",
        fill=FG,
        font=small,
    )

    # Stat cards
    cards = [
        ("Active Jobs", "0", "No active jobs"),
        ("Completed", "12", "All time (demo)"),
        ("Failed", "1", "All time (demo)"),
        ("Today", "$0.00", "of $0.00 limit"),
    ]
    card_w = 230
    for i, (label, value, sub) in enumerate(cards):
        x0 = mx + i * (card_w + 16)
        _rounded(draw, (x0, 160, x0 + card_w, 250), fill=PANEL, outline=BORDER)
        draw.text((x0 + 16, 174), label.upper(), fill=MUTED, font=small)
        draw.text((x0 + 16, 198), value, fill=FG, font=title)
        draw.text((x0 + 16, 226), sub, fill=MUTED, font=small)

    # Month exposure panel
    _rounded(draw, (mx, 270, W - 28, 360), fill=PANEL, outline=BORDER)
    draw.text((mx + 16, 286), "Month exposure", fill=MUTED, font=small)
    draw.text((mx + 16, 312), "$0.00 / $0.00", fill=FG, font=title)
    draw.text((mx + 220, 320), "PAID API FROZEN", fill=YELLOW, font=body)
    draw.text(
        (mx + 16, 338),
        "Settled $0.00  ·  active holds $0.00  ·  unexplained $0.00 (costs doctor)",
        fill=MUTED,
        font=small,
    )

    # Activity + capacity
    _rounded(draw, (mx, 380, mx + 560, H - 28), fill=PANEL, outline=BORDER)
    draw.text((mx + 16, 396), "Recent activity (demo)", fill=FG, font=body)
    rows = [
        ("consult", "Aurora Harbor Pilotage", "local $0", GREEN),
        ("sync", "Temporal Knowledge Graphs", "local $0", GREEN),
        ("research", "blocked metered submit", "frozen", YELLOW),
        ("doctor", "mcp conformance ok", "6 checks", GREEN),
    ]
    ry = 430
    for kind, name, note, color in rows:
        draw.text((mx + 16, ry), kind, fill=MUTED, font=mono)
        draw.text((mx + 100, ry), name, fill=FG, font=body)
        draw.text((mx + 420, ry), note, fill=color, font=small)
        ry += 36

    _rounded(draw, (mx + 580, 380, W - 28, H - 28), fill=PANEL, outline=BORDER)
    draw.text((mx + 596, 396), "Capacity posture", fill=FG, font=body)
    caps = [
        ("Local Ollama", "executable", GREEN),
        ("Plan quota", "visible / gated", YELLOW),
        ("Metered API", "blocked", RED),
    ]
    cy = 440
    for name, status, color in caps:
        draw.text((mx + 596, cy), name, fill=FG, font=body)
        draw.text((mx + 596, cy + 20), status, fill=color, font=small)
        cy += 56
    draw.text(
        (mx + 596, cy + 10),
        "deepr capacity · deepr doctor",
        fill=MUTED,
        font=mono,
    )

    # Status bar
    draw.rectangle([SIDEBAR_W, H - 28, W, H], fill=(18, 18, 20))
    draw.line([(SIDEBAR_W, H - 28), (W, H - 28)], fill=BORDER)
    draw.text((SIDEBAR_W + 16, H - 20), "0 active jobs", fill=MUTED, font=small)
    draw.text((SIDEBAR_W + 140, H - 20), "Today: $0.00", fill=MUTED, font=small)
    draw.text(
        (SIDEBAR_W + 280, H - 20),
        "Month exposure: $0.00 / $0.00  PAID API FROZEN",
        fill=YELLOW,
        font=small,
    )
    draw.ellipse([W - 36, H - 18, W - 28, H - 10], fill=GREEN)
    draw.text((W - 110, H - 20), "Live", fill=MUTED, font=small)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT}")

    # Companion expert hub mock
    hub = ROOT / "assets" / "expert-hub.png"
    img2 = Image.new("RGB", (W, H), BG)
    d2 = ImageDraw.Draw(img2)
    d2.rectangle([0, 0, SIDEBAR_W, H], fill=(16, 16, 18))
    d2.line([(SIDEBAR_W, 0), (SIDEBAR_W, H)], fill=BORDER)
    d2.text((20, 22), "Deepr", fill=FG, font=title)
    d2.text((20, 48), "demo dashboard", fill=MUTED, font=small)
    d2.text((24, 90), "Overview", fill=MUTED, font=body)
    d2.rounded_rectangle([12, 124, SIDEBAR_W - 12, 156], radius=12, fill=(32, 40, 56))
    d2.text((24, 130), "Experts", fill=PRIMARY, font=body)
    d2.text((mx, 24), "Expert Hub", fill=FG, font=title)
    d2.text((mx, 52), "Persistent domain experts  ·  demo data", fill=MUTED, font=small)

    experts = [
        ("Temporal Knowledge Graphs", "100 claims · fresh · local", "HEALTHY"),
        ("Model Context Protocol", "180 claims · dual-era MCP", "HEALTHY"),
        ("Aurora Harbor Pilotage", "demo expert · $0 consult", "DEMO"),
        ("Digital Continuity", "self-model + monitor", "HEALTHY"),
    ]
    ey = 100
    for name, meta, badge in experts:
        d2.rounded_rectangle([mx, ey, W - 28, ey + 100], radius=12, fill=PANEL, outline=BORDER)
        d2.text((mx + 20, ey + 18), name, fill=FG, font=body)
        d2.text((mx + 20, ey + 44), meta, fill=MUTED, font=small)
        color = GREEN if badge == "HEALTHY" else PRIMARY
        d2.text((W - 140, ey + 20), badge, fill=color, font=small)
        d2.text((mx + 20, ey + 70), "next: blueprint · sync --local · eval expert-value", fill=MUTED, font=mono)
        ey += 116

    img2.save(hub, "PNG", optimize=True)
    print(f"Wrote {hub}")


if __name__ == "__main__":
    main()
