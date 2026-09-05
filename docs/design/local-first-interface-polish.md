# Local-first interface polish

Status: implementation candidate, September 5, 2026. This corrects existing
interface behavior and presentation without adding execution authority.

## Problem

The dashboard's first-run journey recommends setting a budget and running
paid research even though its own capacity banner says paid dispatch is
blocked. Expert cards are clickable containers outside keyboard navigation,
profiles default to blocked browser chat, and the mobile status bar overflows
its available width. Filled status colors and opacity-based hover treatments
lose text contrast. The app and favicon use different versions of a rune-based
mark, which does not match the intended original geometric identity.

## Intended experience

Keep the existing IBM Plex Sans and JetBrains Mono, warm light canvas, dark
raised surfaces, petrol teal, restrained spacing, and compact interface.
Polish the path from a local workspace to an inspectable expert and retained
evidence. Clear next actions lead to supported local creation or explicit CLI
handoffs; they do not imply browser-local chat or paid research is executable.

Metered research remains a clearly labeled preview or unavailable capability.
Browser chat stays visible with an accurate blocked state; evidence inspection
is the default profile view. Empty data, failed loading, and unmatched filters
have distinct messages and actions. Shared page headings wrap at small widths.

Expert cards become real links with visible keyboard focus. Current sidebar
navigation exposes its active state to assistive technology. The status bar
retains connection and paid-dispatch posture on a narrow screen, with full
accounting available through an accessible labeled control or destination.
Financial unknowns remain unknown; compact text cannot turn unavailable
accounting into a zero balance or an execution-ready indication.

## Identity and tokens

Use one original geometric mark with two nested open contours: an open well.
The outer shape suggests retained knowledge, the inset suggests depth, and
the open top leaves room for new evidence and revision. Meaning supports the
identity; it is not a claim of semantic understanding or quality. Keep broad
negative space and a simple silhouette at 16, 20, 24, and 32 pixels.

The editable SVG geometry is shared by the app and favicon, with no duplicate
hand-drawn variant. The wordmark remains live text. Use no rune, rays, mystical
glyphs, decorative sparkle, author credit, or new typeface dependency.

Use explicit filled-control hover colors instead of translucent primary
backgrounds. Noninteractive badges do not change color on hover. Check all
supported accent choices and both themes against actual composited colors.
Normal text aims for at least 4.5:1 contrast, with margin rather than rounding
a failing value up. This targeted work is not a whole-app accessibility
certification.

## Live validation status

The plan-quota probe's JSON mode must preserve its structured payload while
returning a nonzero process status when the probe fails. Previously the human
output path failed correctly but JSON returned success, so scripts could
mistake an overage-proof refusal, expired session, or exhausted quota for a
working adapter. Successful probes remain exit 0, failed round trips are exit
1, and pre-dispatch safety refusals remain exit 2. No probe failure changes
the adapter's spend authority or enables fallback.

The web Create Expert action must persist a local profile, matching its
zero-cost presentation. The old constructor inherited the default API provider,
API model, and positive monthly learning budget even though creation made no
provider request. Set the local provider and model, a local-only store marker,
and a zero monthly learning budget explicitly. Detecting an available local
model is read-only; an unavailable runtime leaves an untrained local profile.
Creating that profile still performs no inference or learning and grants no
metered authority.

Creating an expert also clears the active name filter and selects the full
roster. Previously a successful creation stayed hidden behind the flagship
filter or an unrelated search. A browser regression creates an expert from
that filtered state and requires its native profile link to become visible.

The live profile check also exposed missing study metadata in the detail API.
Return the same derived study counters as the roster, so a studied expert does
not display zero findings on its own page. The knowledge-count read opens its
belief store read-only and must not create directories for an untrained expert.

## Boundary and alternatives

This increment changes navigation semantics, copy, responsive presentation,
shared color tokens, and brand assets. It does not add backend endpoints,
provider requests, local model dispatch, canonical expert writes, credentials,
cloud deployment, automatic actions, or new spend authority. Existing commands
and forms retain their current gates.

A new component library, broad routing rewrite, or alternate visual theme
would add migration cost without fixing these observed problems. Pretending
blocked controls work would obscure the product's actual state. The correction
uses the current components and supported local workflow instead.

## Validation and promotion

Use isolated browser fixtures with intercepted API responses for empty,
populated, loading-error, and unmatched-search states. No real provider or
expert mutation is necessary. Exercise keyboard navigation, visible focus,
active-link semantics, and 320px/390px reflow. Inspect light and dark screenshots
and render the logo at actual favicon and sidebar sizes. Verify filled-control
contrast at rest and hover for all supported themes and accents.

Run frontend lint, TypeScript/build, behavioral tests, and the repository's
Python and packaging gates. Keep the existing main release usable while this
candidate is reviewed. Publish screenshots and documentation only from the
validated implementation, clearly identifying any synthetic fixture roster.

## Primary references

- [W3C text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
  covers normal interface text and hover states.
- [W3C keyboard access](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html)
  motivates native links and keyboard-operable controls.
- [W3C reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)
  motivates narrow-screen checks without loss of information or function.
- [IBM typeface guidance](https://www.ibm.com/design/language/typography/typeface/)
  supports retaining the existing self-hosted type family.
