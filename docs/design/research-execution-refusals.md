# Research execution refusals

Issue 201 exposes a CLI contract failure: an unconfirmed budget returned normally,
so research could exit successfully without a job or result. Execution also
reselected the provider after preview had resolved a different route.

## Decision

- Resolve the ordinary research route once. Preview, admission, and execution use
  that provider and model. Keep current defaults and routing exclusions.
- Preview stays write-free and needs no credential. Execution checks credential
  presence through the existing process, quarantine, and stored-key inventory
  before cost confirmation or reservation. Presence is not validity or spend
  authority; no key is released by this check and no online probe runs.
- Validation, missing credentials, bounded admission, cancellation, and budget
  refusal terminate with a nonzero exit. Human errors go to stderr; JSON failures
  use the existing `deepr-cli-operation-result-v1` envelope, with stable error
  codes and no prompt or accompanying text. Invalid batch input uses the same
  boundary before router construction; company input errors retain an invocation
  example so the operator can recover.
- Explicit attended OpenRouter keeps its one pinned no-tool completion, wallet,
  owner ceiling, account evidence, reservation, credential recheck, and settlement
  requirements. JSON, quiet, and noninteractive OpenRouter execution are refused
  even when stored authority is present. A terminal and per-invocation confirmation
  are required; `-y` is not attended consent. Preview remains available in every
  output mode. Other paid execution eligibility and fallback rules do not change.

## Alternatives

Changing the default provider to OpenRouter would change product routing and spend
scope, so this repair does not do it. Returning bare Click errors for JSON would
break machine consumers. Checking only exported environment keys would misclassify
credentials intentionally held in quarantine or stored by `deepr keys set`.

## Verification

Exercise the real Click handler and execution boundary offline with provider
construction, reservation, and submission blocked where refusal must precede them.
Cover absent and stored/quarantined keys, budget refusal and cancellation, invalid
query/upload/limit, route continuity, keyless preview, and attended OpenRouter's
noninteractive refusal. Retain existing bounded-accounting and settlement tests.
