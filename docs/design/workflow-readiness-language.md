# Workflow Readiness Language

Status: accepted for current first-run and diagnostic surfaces in v2.37
development.

## Problem

Deepr has strong dispatch-time safety gates, but several earlier presentation
surfaces compress different evidence into the word `available`. A local runtime
can be detected, a plan CLI can be installed, and an API credential can be
configured without proving that a particular workflow can execute safely now.
Init and base capacity also described one global local to plan to metered
waterfall even though current routing is workflow-specific.

This mismatch is a product trust defect. A later dispatch refusal prevents an
unsafe call, but it does not make an earlier readiness claim true.

## Evidence Levels

Current surfaces use these terms narrowly:

1. **Detected**: a local runtime responded to a local probe.
2. **Installed**: a plan CLI executable exists on `PATH`. This says nothing
   about authentication, native-tool confinement, transcript behavior, quota,
   paid overage, or task support.
3. **Configured**: a metered API credential is present. This says nothing about
   credential validity, current model support, price coverage, tool bounds, or
   operator authority to spend.
4. **Eligible**: the workflow-specific deterministic safety gate has enough
   evidence to allow a named path. `capacity fleet` explains plan-adapter
   blockers and `capacity next` derives safe local-maintenance actions.
5. **Authorized**: the operator has explicitly approved the exact bounded
   action. A budget ceiling can reject excess spend, but never supplies this
   authority.

Base `capacity` remains a read-only inventory. Its compatibility JSON keeps the
existing `available` field, but adds the evidence basis and reports execution
eligibility as unknown. Human output never uses `available` for an installed
plan CLI.

## First-Run Sequence

The current safe sequence is:

1. `deepr init`
2. `deepr doctor --skip-connectivity`
3. `deepr capacity`
4. `capacity next` for detected local capacity, `capacity fleet` for a
   registered installed plan adapter, or an exact API research preview;
   unadapted plan-style CLIs remain inventory-only
5. An explicit local or safety-eligible plan expert command, or an exact
   metered research preview
6. Explicit authorization for any later metered execution

`deepr doctor` without `--skip-connectivity` intentionally contacts configured
OpenAI, Gemini, and xAI providers. Anthropic and Azure are reported as
configured but are not live-validated. Plain doctor is optional, not the
default no-network onboarding step.

## Diagnostic Closing Rules

Doctor closing guidance is deterministic:

- Any `ERROR` blocks success copy and new-work recommendations.
- A stale queue warning takes precedence over starting more work and prints
  read-only inspection commands.
- Missing metered API keys are informational because local and explicit plan
  expert workflows do not require them.
- A healthy keyless setup points to base `capacity`, which branches from the
  evidence it actually observes.
- A healthy API-configured setup points to a no-spend research preview, not a
  live request.
- Provider exception text never crosses the console boundary. Fixed copy
  preserves failure visibility without echoing provider-controlled or
  credential-adjacent content.

## Non-goals

- A new shared readiness schema or live dashboard readiness panel.
- Changing dispatch, quota, admission, budget, or provider-selection logic.
- Claiming that base capacity can prove plan execution eligibility.
- Queue and reservation reconciliation beyond the current read-only aggregate
  warning.

Those need separate versioned contracts. This change corrects current claims
without widening runtime authority.
