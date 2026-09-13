# Claude managed-policy containment

Status: compatible safety correction, September 13, 2026. This decision closes
an unproven execution path and grants no new authority.

## Problem and evidence

Deepr permits Claude plan execution after its static safety gate and live
paid-overage check. Its command uses safe mode, empty model tools, an empty MCP
configuration, and disabled session persistence. Those controls do not establish
that the process has no independent command execution.

The current official [CLI reference](https://code.claude.com/docs/en/cli-reference)
says managed-policy hooks and certain managed command settings survive safe
mode. The [hooks reference](https://code.claude.com/docs/en/hooks) documents
session-start execution and explains that lower-precedence settings cannot
disable managed hooks. The [settings precedence contract](https://code.claude.com/docs/en/settings)
includes managed sources beyond checkout-local files. These pages were checked
September 13, 2026. This is a conditional defect established from the dispatch
path and provider documentation; no hook was executed and no claim is made
about policy installed on a particular machine.

A machine or account with a managed session-start command can therefore run
that command independently of the empty model-tool catalog. Deepr's scratch
working directory, environment allowlist, and process lifetime controls do not
provide filesystem or network confinement for it. A successful quota probe or
disabled provider overage does not bound a hook's independent side effects.

## Decision

Mark the production Claude adapter execution-blocked using the existing adapter
safety contract. Reject before quota probes, live account-control observations,
runner construction, or provider work. Keep inventory and offline fixtures
available. Stored subscription authentication and the live overage mechanism
remain prerequisites for any later restoration, not substitutes for confinement.

The local Ollama expert workflow remains the executable rehearsal lane. Current
documentation must say that no production plan adapter is execution-eligible;
historical successful probes remain historical transport and billing evidence.
Do not reinterpret their results as proof against managed policy.

## Alternatives rejected

- Adding a lower-precedence setting to disable hooks: it cannot override managed
  hooks and would create a false safety claim.
- Checking only a local managed-settings file: server, registry, and device
  policy sources make that incomplete.
- Trusting an empty API-key environment, an empty tool list, or explicit plan
  selection: none confines independent child-process effects.
- Running a live hook experiment: unnecessary for the fail-closed correction
  and could create the very external side effects under review.

## Verification and restoration

Regression tests must show production Claude refusal with empty and populated
environments and prove that quota/account probes and subprocess runners are
not reached. Tests of the dormant transport and overage mechanisms must use an
explicit synthetic eligible adapter, never weaken the production registry.
Run the full no-key unit suite, coverage gate, lint, format, type, documentation,
and money-boundary checks.

Restoration requires evidence for the exact runtime version and all effective
managed-policy sources, or independently enforced process confinement that
prevents unaccounted network and credential effects. A version string, settings
snapshot, or operator acknowledgment alone is insufficient. Any proposed
restoration gets a separate reviewed design and validation record.
