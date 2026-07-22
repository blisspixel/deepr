# Dashboard Authentication Session

Status: implemented for the experimental local dashboard in v2.37 development.

## Problem

The server already required `DEEPR_API_KEY` for protected HTTP routes and
Socket.IO connections, but the browser mounted the full application shell
before it could prove access. HTTP and Socket.IO independently read an
undocumented persistent browser key. A protected launch therefore looked like
an offline backend and offered no supported way to provide the configured
token.

## Goals

- Prove access through a read-only protected endpoint before mounting the
  application shell.
- Preserve explicit tokenless loopback mode.
- Use one credential for HTTP and Socket.IO.
- Keep the credential within the current browser tab session.
- Distinguish a rejected token, missing server authentication, an unreachable
  server, and an unexpected response without exposing server details.
- Return to the gate if a later protected request receives HTTP 401.

## Non-goals

- User accounts, roles, delegated identity, refresh tokens, or remote session
  management.
- TLS termination or permission to expose the development server beyond
  loopback.
- Changing the server's shared-secret validation or the explicit
  unauthenticated-loopback launch contract.

Tokenless loopback mode is not safe behind a reverse proxy, tunnel, or port
forward because the application evaluates the immediate peer address. Remote
access must retain `DEEPR_API_KEY` and use an HTTPS-capable reverse proxy.

## Contract

1. The browser removes the obsolete persistent `api_token` value without
   migrating it.
2. The access gate reads the current tab credential and requests
   `/api/cost/limits`, a protected read-only configuration endpoint with no
   queue enumeration or provider call.
3. HTTP 200 mounts the application shell. If the successful probe used a
   token, the browser stores its trimmed value in `sessionStorage`. If browser
   storage is unavailable, module-scoped memory preserves the same tab-local
   lifetime.
4. HTTP 401 clears the session credential and shows the token form.
5. HTTP 503 with `AUTH_NOT_CONFIGURED` shows operator configuration guidance.
6. No response shows server-start guidance. Any other response shows a fixed
   unexpected-response state and directs the operator to local logs.
7. An auth-attempt generation rejects late probe results. A 401 event is
   applied only when its presented credential still matches the current
   session, so an old request cannot clear a newly verified token.
8. AppShell mounts only after step 3, so Socket.IO cannot connect before the
   shared credential has been proven. Both transports use the same accessor.
9. A later HTTP 401 emits an in-process auth-required event. The gate clears
   the credential, unmounts AppShell, and returns to the token form.

The token is never copied into query keys, application URLs, rendered error
text, local logs, or persistent `localStorage`.

## Alternatives Rejected

- Continuing to read `localStorage`: it outlives the tab and preserves a secret
  without an explicit product surface.
- Rendering the shell and adding a token field in Settings: every protected
  query fails before the user can reach a trustworthy settings workflow.
- Treating HTTP 401 as offline: it hides an actionable access condition and
  causes unnecessary server troubleshooting.
- Making `/api/jobs/stats` public: this would weaken the existing server
  boundary only to simplify bootstrap.

## Verification

- Pure tests cover normalization, clearing, legacy-token removal, denied
  browser storage, bearer extraction, shell-mount authorization, stale-request
  correlation, and stable access-error classification.
- Source-wiring tests require AppShell to remain inside the gate and require
  both HTTP and Socket.IO to use the shared session accessor.
- Frontend lint, TypeScript compilation, unit tests, and production build are
  blocking local checks.
- Local server probes cover tokenless loopback, missing token, wrong token, and
  correct token without provider or paid calls.
