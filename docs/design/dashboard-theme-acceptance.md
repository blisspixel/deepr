# Dashboard light/dark acceptance in CI

Decision for #236, 2026-10-18, before implementation. Keep existing synthetic route/browser regressions, and
add actual built-dashboard screenshots against a fresh isolated Flask backend.
Use the production built frontend from the existing npm build, so API and assets
share one loopback origin and no development proxy or additional server is needed.

A bounded helper creates a private temporary runtime and passes only explicit
safe environment variables: config/data/queue/expert/report/cost roots all beneath
it, dotenv disabled, demo opt-in, unauthenticated loopback opt-in, no provider keys.
Verify canonical resolved roots before seeding. Demo records are synthetic and
must be labelled as such in evidence; do not imply a formed/calibrated expert.
Load demo data once before the two sequential theme runs. No operator paths are
cleared; no provider or model dispatch is part of this check. A server-side
outbound-socket guard refuses every outgoing connection, including loopback;
serving browser requests needs no outgoing connection.

Exercise the existing screenshot-qa.mjs against this backend for light and dark.
Keep over-budget refusal enabled and at most the existing $5 application ceiling.
Add output-root configuration and assertions for the applied theme, visible route
content, failed navigation and uncaught browser errors. Reject nonlocal browser
requests. Preserve raw screenshots and a structured receipt as CI artifacts;
do not touch the frontend distribution archive except through its owning build.

The helper waits for actual readiness, retains backend/QA logs, and always stops
its own process, including on failure. Tests cover bounded lifecycle/error cleanup
and screenshot assertions where behavior changes. Run locked npm lint/tests/build,
existing 102 browser checks, both real-backend theme runs and inspect captures.
Close tracker only after its dependent terminal issues and this acceptance pass.

Baseline preparation found the existing demo seed has $1.83 of synthetic job
history; a correctly frozen $0 account causes screenshot-qa's cost guard to
refuse it. Preserve that refusal. An environment ceiling of $5 cannot unfreeze
the account (and its effective cap correctly remains zero). For CI screenshots,
provide explicitly zero-cost synthetic demo rows before the canonical seed
writes jobs or ledger entries. Do not erase/reconcile positive history, grant
wallet/account authority, override the screenshot guard or hand-edit outputs.
Keep provider calls zero and paid API frozen. The baseline used an instrumented
copy of the existing QA solely to redirect output, observe browser errors and
refuse external requests; the production frontend/source were untouched.
Readiness must call /api/health and parse its JSON status: /health is served by
the SPA fallback and its HTTP 200 is not a backend-health assertion.

The real-backend light baseline exposed errors hidden by Vite/mocked-route QA:
12 blocked inline theme scripts and blocked embedded data-font loads under the
existing `script-src 'self'` / `font-src 'self'` CSP, plus one QA init-script
localStorage error per initial opaque page. Preserve that evidence; screenshots
without console assertions are not acceptance. Prefer a self-hosted external
theme initializer and external font assets over relaxing CSP. The QA theme can
be installed using origin-scoped Playwright storageState instead of an init
script on every opaque about:blank document. Verify actual stacks first and
retain unchanged production CSP assertions. Real HTTP routes have no failing
responses or external requests in this baseline.

Installed Vite 8.1.5 accepts assetsInlineLimit as a number or a callback returning
boolean/undefined. Preserve strict production headers: move the existing theme
initializer verbatim to a self-hosted public script and prevent fonts from being
inlined (a font-extension callback can leave other asset defaults unchanged).
Real-backend checks should assert requested/applied theme and initial paint in
addition to no uncaught/page/console errors. Origin-scoped storageState avoids
the current opaque-page init-script failure. Current inline initializer already
catches storage denial; retain that graceful behavior when externalizing it.

First-paint proof should keep production bytes: pause same-origin /assets/*.js
module requests in Playwright, navigate only to response commit, wait for the
blocking public theme initializer to set the requested root class/accent, and
record that state while the application module is still held. Release requests
in finally, then await actual app content and capture the unchanged page.
This proves appearance initialization before React without replacing scripts,
relaxing CSP or calling a post-React class check a first-paint result. Scope the
pause route to the exact local origin and release on timeout/error before
closing the page/context. Preserve no-console-error assertions throughout.

Final isolation review reproduced the parent JSON reader honoring inherited
HTTP proxy variables even for loopback health reads. A synthetic local proxy
received the request and supplied its own response. Use an explicit empty proxy
handler for direct local reads; a real two-server loopback regression must see
only the owned backend receive the request. Preserve the failing and repaired
trials. This changes QA transport isolation, not production networking policy.
