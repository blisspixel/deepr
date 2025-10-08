# Deepr Branding Guidelines

## Tagline

**Knowledge Is Power, Automate It**

## Philosophy

Deepr is about going deep—deep research, deep analysis, deep understanding. The brand should reflect:
- Depth and thoroughness
- Professional competence with a hint of snark
- CLI-first, developer-focused tools
- No-nonsense pragmatism

## Tone

- **Clean and professional** - This is serious research automation
- **Dev-friendly humor** - A bit of snark, but not annoying
- **No emojis** - We're CLI-first. ASCII art is fine, emojis are not
- **Direct and honest** - Tell users the truth (especially about costs)

## Color Palette

### Primary: Deep Blue (#1a5490)
The color of depth, knowledge, and trust. Blue conveys expertise and reliability without being boring.

### Secondary: Slate Gray (#475569)
Professional, clean, pairs well with terminal backgrounds.

### Accent: Electric Cyan (#22d3ee)
For highlights, success states, and call-to-action elements. Stands out without being garish.

### Warning: Amber (#f59e0b)
For cost warnings and budget alerts. Gets attention without panic.

### Error: Crimson (#dc2626)
For errors and stop conditions.

**Why not orange/coral?** That's Claude Code's color. We respect their brand. Deepr is about depth (blue) and precision (cyan accents), not surface-level exploration.

## ASCII Art

All CLI branding uses pure ASCII characters (#, =, -, etc.) for maximum cross-platform compatibility:

```
===============================================================================

    ########   ##########  ##########  ########      #######
    ##    ##   ##          ##          ##     ##     ##    ##
    ##     ##  ########    ########    ########      ########
    ##    ##   ##          ##          ##            ##    ##
    ########   ##########  ##########  ##            ##     ##

               Knowledge Is Power, Automate It

===============================================================================
```

## Voice Examples

### Good Examples

**Cost warnings:**
> "Deep Research API calls can be expensive. Seriously expensive if you're not careful."

**Feature descriptions:**
> "Local SQLite queue - Fast, reliable, zero setup. Perfect for workstation deployments."

**Documentation tone:**
> "Pro tip: Start with o4-mini-deep-research for testing. It's cheaper and you can validate your setup without burning budget."

### Bad Examples

**Too cutesy:**
> "Oops! Looks like you forgot your API key! 😅"

**Too corporate:**
> "Deepr leverages synergistic AI capabilities to maximize research throughput."

**Too snarky:**
> "Did you even read the docs? RTFM."

## Usage in Code

- Informational messages: Use standard output
- Warnings (costs, limits): Use clear language + amber color in terminals that support it
- Errors: Use direct language + error color
- Success: Minimal celebration, just confirm it worked

## Terminal Output

- ASCII art for branding
- Cross-platform symbols (CHECK, CROSS) from `deepr.branding`
- No Unicode emojis or fancy box-drawing characters
- Clean separation between sections
- Readable on light and dark terminal backgrounds

---

**In summary:** Professional, direct, occasionally snarky, always honest. Think "helpful senior dev who's seen some stuff" not "corporate marketing drone" or "meme-obsessed junior."
