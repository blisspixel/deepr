# Web interface design language

Updated September 5, 2026. The initial typography and surface refresh shipped
in June. The current local workflow and identity changes are specified in
[Local-first interface polish](local-first-interface-polish.md).

## Current implementation

Deepr uses a compact research workspace with clear evidence, capacity, and
accounting states. Presentation should help people inspect an expert and find
the next supported action. A visually complete control cannot imply that a
blocked operation is executable.

- **Type:** self-hosted IBM Plex Sans for interface text and JetBrains Mono
  for data. Body text uses normal font features; `.data-figure`,
  `[data-figure]`, and numeric cells opt into tabular numerals. The interface
  scale runs from 11px labels through 13px controls and 18px page titles.
- **Color:** warm neutral light surfaces, dark raised surfaces, and petrol
  teal by default. Eight selectable accents retain the same semantic roles.
  Filled buttons have explicit hover tokens; noninteractive badges do not
  change color on hover. Unknown financial state is labeled unknown.
- **Shape:** the base radius is `0.3125rem` (5px at the default root size).
  Smaller control radii derive from that token. Borders establish hierarchy;
  shadows are reserved for popovers and dialogs.
- **Identity:** one editable `public/deepr.svg` supplies the favicon and app
  mark. Two open, nested contours suggest retained knowledge, depth, and room
  for revision. The wordmark remains live text.
- **Navigation:** expert cards are native links with visible keyboard focus.
  Profiles open on Claims and retain saved chat inspection. Local consultation
  has an explicit PowerShell command handoff. Browser chat and paid research
  retain their execution gates.
- **States:** loading failures, empty workspaces, and unmatched searches have
  different messages. Filtering keeps the input mounted and focused. The
  compact status bar retains connection and paid-dispatch state on mobile,
  with a labeled route to full accounting.

The authoritative tokens and type scale are in
[`src/index.css`](../../src/deepr/web/frontend/src/index.css). Shared control
variants live in the existing `components/ui` directory. Changes should use
these roles rather than introduce page-specific colors or another library.

## Verification

Run frontend lint, the Node behavioral suite, and the production build from
`src/deepr/web/frontend` using the versions in `package.json`. Run
`node qa/local-ui.mjs` for isolated browser fixtures. It intercepts API and
socket traffic and labels its content synthetic; it does not validate real
provider execution or expert quality. Captures go to `screenshots/local-ui`
unless `QA_OUTPUT` selects another directory.

The September validation covers both themes at 320, 390, and 1440px, keyboard
navigation, saved conversations, unavailable actions, and accounting states.
The identity checks also render 16, 20, 24, and 32px marks and verify filled
control contrast across all supported accents. These are targeted checks,
not a whole-app accessibility certification.

README images must come from the built application. Any synthetic roster must
be identified as a fixture. An isolated copy of real expert state can show a
live workflow without writing the maintainer's canonical experts.

## References

- [IBM typeface guidance](https://www.ibm.com/design/language/typography/typeface/)
- [W3C text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
- [W3C keyboard access](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html)
- [W3C reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)
