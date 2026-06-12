# Design: Web UI Refinement (de-slop pass)

Target: incremental, token-level first. Status: phase 1 shipped 2026-06-12.

## Problem

The dashboard reads as "unthemed shadcn template" - what the June 2026
design discourse calls the AI-slopware look. The community has converged
on a concrete list of tells (Developers Digest's 16-pattern audit,
Anthropic's frontend-aesthetics skill with 277k installs, the Taste
anti-slop skill): Inter everywhere, the default shadcn blue/purple,
gradients and glows, glassmorphism, colored-left-border cards,
icon-topped identical feature cards, centered heroes.

Audit of deepr's frontend against that list (2026-06-12):

| Tell | Present? |
|------|----------|
| Inter as primary font | YES - tailwind config + index.css body |
| Default shadcn primary (221.2 83.2% 53.3% blue) | YES - the literal template value |
| Default shadcn radius/neutrals throughout | YES |
| Glassmorphism | One use (app-shell header) + two unused utilities |
| Gradients / large glows | No (clean) |
| Colored-left-border cards | No (clean) |
| Emoji sidebar icons | No - Lucide, professional |
| Stat banner rows / centered hero | No (it is a dashboard, density is appropriate) |
| Permanent dark mode | No - light/dark/system via store |

So the bones are good; the slop signal comes almost entirely from
*unthemed defaults*, not from structural kitsch. That is the cheapest
possible fix: re-theme the tokens, leave the layout alone.

## Direction: research instrument, not SaaS template

One strong opinion, committed to (the anti-slop literature's actual
advice): deepr is a lab instrument for research operations. Instrument
panels are dense, monochrome, typographically precise, with one decisive
accent color and data rendered in monospace.

### Phase 1 - tokens (shipped)

1. **Type**: IBM Plex Sans replaces Inter for UI text; JetBrains Mono
   (already the mono stack) for data. Plex is IBM's instrument-heritage
   face, pairs natively with the existing mono choices, is absent from
   every slop-tell list, free, and self-hosted via @fontsource (no CDN,
   works offline, deterministic builds). `font-feature-settings` enables
   tabular numerals body-wide so metrics align.
2. **Accent**: one decisive petrol teal replaces the default shadcn blue
   across primary / ring / sidebar-primary / chart-1 (light
   `hsl(172 65% 30%)`, dark `hsl(172 50% 48%)`). Semantic status colors
   (success/warning/info/destructive) stay; info shifts slightly cyan to
   keep distance from primary.
3. **Shape**: radius 0.5rem -> 0.375rem. Subtly more technical; still
   soft enough for the existing components.
4. **Surfaces**: the one glassmorphism use becomes a solid surface with a
   border; the `.glass`/`.glass-heavy` utilities are removed.

### Phase 2 - component-level (later, as touched)

- Key metrics (cost figures, token counts, job ids, model names) render
  in mono via a `data-figure` utility - overview stat cards first.
- Chart palette alignment pass once real expert data is on screen.
- Density review of the results-library table (instrument panels are
  dense; current spacing is slightly generous).
- Empty states: replace generic "no data" copy with instrument-style
  zero-readings.

## Non-goals

- No layout rewrites, no new component library, no landing-page
  aesthetics (this is an operations dashboard).
- No dark-mode-only commitment; the three-way theme stays.
- No animation additions - the existing reduced-motion support and
  restrained transitions are already right.

## Verification

Phase 1 ships behind the existing frontend CI gate (eslint zero-warnings,
tsc, vite build) and a programmatic screenshot regeneration
(`scripts/capture_screenshots.py`) so the README reflects the refresh.

Sources reviewed 2026-06-12: Developers Digest "AI Design Slop: 15
Patterns That Out Your App as Vibe-Coded"; Anthropic frontend-aesthetics
skill discourse; Taste anti-slop skill review (andrew.ooo); shadcn
theming docs.
