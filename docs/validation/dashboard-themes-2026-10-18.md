# Production dashboard theme validation, 2026-10-18

Issue #236. [Design](../design/dashboard-theme-acceptance.md). These captures
exercise the production build on the actual Flask backend with isolated canonical
synthetic demo state. They do not establish expert quality, currentness or S0.

The retained pre-fix light/dark baseline exposed 12 blocked inline initializers
and 72 blocked embedded font loads per theme under production CSP, plus QA
storage errors on opaque initial pages. A strict pre-fix build then failed the
before-application theme check. These failed trials remain retained separately.

The existing initializer is now a blocking self-hosted head script, and font
assets are self-hosted files. Production `script-src 'self'` and `font-src 'self'`
remain unchanged. Existing accent hydration/contrast checks retain their
assertions against the owning script; storage denial remains graceful.

Both repaired themes pass all 12 routes, with 24 PNG captures, zero console or
page errors, zero failing HTTP responses and zero external browser requests.
Each route records requested theme and accent initialization while the unchanged
application module is paused, before React mounts. The module is then released
and the real page and fonts load before capture. This is a before-application
initialization check, not a physical monitor or browser paint-timing claim.

Final isolation review also reproduced a parent health request going through
an inherited HTTP proxy. The retained regression receives `proxy` instead of
the owned backend's `healthy` response before repair. An explicit empty proxy
handler now connects directly; a real two-server loopback test confirms that
only the backend receives the request. The caller's environment stays unchanged.

The helper binds private config/data/queue/expert/report/cost roots before
imports, drops credentials and caller QA overrides, verifies its own JSON health
response and always stops its backend. Its outbound socket guard records and
refuses every server connection attempt. The actual run records zero attempts,
a frozen $0 ceiling and zero ledger spend. Synthetic zero-cost jobs are selected
before canonical seed writes; no positive history is erased and no wallet or
account authority is granted. Expert metadata in these synthetic fixtures may
contain historical display costs; these are not ledger spend or real research.

The existing browser suite passes 102 layout/state checks at 320, 390 and 1440
pixels in both themes. All 89 frontend unit cases pass, locked lint/build pass,
and npm audit reports zero vulnerabilities. Forty focused Python packaging,
helper lifecycle and production header cases pass, with one existing optional
skip. The final frozen revision passes 13,462 offline cases with 22 existing
skips and 85.53% combined coverage; the independent coverage gate passes. The
pre-proxy-fix full trial (13,461 cases, 85.52%) remains retained separately.
Exact-head/resulting-main CI remain publication requirements.
The candidate clean wheel passes both MCP protocol eras and the host profile;
all six offline conformance checks pass at $0 with no network or state writes.
Plugin builds agree byte for byte, and a locked frontend rebuild matches the
packaged archive. All 293 strict islands pass on both floor and promoted types;
the two presentation modules also pass strict checking.

Visual review covers all 24 pages through contact sheets, with full-size review
of overview, expert claims, costs and settings. No clipped layout or theme/font
failure was observed in these desktop captures. See the actual
[light overview](../../assets/qa/dashboard-themes/light-01-overview.png),
[dark overview](../../assets/qa/dashboard-themes/dark-01-overview.png),
[light expert](../../assets/qa/dashboard-themes/light-07-expert-profile.png),
[dark expert](../../assets/qa/dashboard-themes/dark-07-expert-profile.png) and
[receipt](../../assets/qa/dashboard-themes/receipt.json). CI retains all captures
and failure evidence for three days. No provider or model call is part of QA.

No current codegraph was available; owning source, callers and tests were traced
directly. Frontend archive generation uses the existing deterministic build owner.
