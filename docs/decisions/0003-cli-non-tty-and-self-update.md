# 0003. CLI: non-TTY safety and self-update

- Status: Accepted
- Date: 2026-06-12

## Context

The CLI best-practices review flagged two QOL gaps. (1) `deepr` with no
arguments always launched interactive mode - meaningless and potentially
confusing when driven by a script, CI, or an AI agent (a non-interactive
stdin). (2) There was no in-tool update path; modern CLIs (claude, codex,
grok) self-update and tell the user when a newer version exists.

## Decision

- No-args `deepr` launches interactive mode only when stdin is a TTY;
  otherwise it prints help and exits 0 (clig.dev: never start interactive
  elements for a non-interactive caller).
- Add `deepr upgrade` (with `--check`), which detects the install origin
  (pipx / pip / editable source) and runs the right update; reads the latest
  version from the PyPI JSON API; degrades gracefully offline and for
  editable checkouts. The install one-liners become idempotent (re-run to
  update) with uninstall support.

## Alternatives considered

- **Keep no-args -> interactive always.** Rejected: it is a footgun for the
  agent/CI consumers deepr explicitly targets.
- **A background "update available" nag on every command.** Rejected:
  noisy, and network-on-every-invocation is the opposite of good CLI
  citizenship. Updates are explicit (`upgrade`/`upgrade --check`).
- **Bundle a standalone binary (PyInstaller/shiv).** Rejected for now:
  pipx/pip distribution fits a Python package with compiled deps; revisit if
  a zero-Python install becomes a real user need.

## Consequences

- Scripts and agents that run bare `deepr` get help, not a hung menu.
- Updating is one command regardless of how deepr was installed; the network
  call is bounded and opt-in.
- No new dependencies (stdlib `urllib` + `subprocess`).
