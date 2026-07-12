# Design: scheduled local capacity contention

Status: shipped for scheduled sync, sync-all, local route-gaps, and the local
recall-embedding substep of plan-backed compiled sync.

## Goal

Scheduled local expert maintenance should be polite to other GPU work. Before a
scheduled local model dispatch, Deepr takes one read-only, best-effort occupancy
observation. Confirmed contention produces a durable waiting outcome and a
bounded retry time. It never kills another process, waits inside the current
process, or falls through to plan-quota or metered API capacity.

This is a capacity and side-effect decision. It does not judge research meaning
or model quality.

## Scope and operator boundary

The bounded surface covers `expert sync --scheduled`,
`expert sync-all --scheduled`, `expert route-gaps --execute --scheduled` when
the selected fill backend is local, and plan-backed scheduled compiled sync
when `--recall-embedding-model` adds a local Ollama embedding substep. All use a
shared wait recorder.

- A scheduled run selected onto local capacity checks occupancy before model
  client or maintenance-engine construction.
- A confirmed `busy` observation stops with `ExpertLoopRun.status=waiting` and
  `stop_reason=capacity_unavailable`.
- `expert sync --local` and `expert sync-all --local` without `--scheduled`
  remain explicit operator overrides and do not check occupancy.
- Dry runs do not dispatch a model and do not wait on occupancy.
- A busy local rung never falls through to a plan CLI or metered API. A later
  host-scheduler invocation re-enters the normal waterfall from the start.
- A plan-backed compiled sync with a busy local recall embedder waits before
  constructing either client. The outer plan capacity does not make the local
  substep free of hardware contention.
- Scheduled local route-gaps checks before gap-fill engine construction. Manual
  route-gaps and unknown platform observations continue unchanged.

## Requested-operation contract

Every local-busy wait carries the semantic retry command as structured argv.
The canonical field is `requested_operation.command_argv`, a list of argument
strings that never passes through a shell. `next_action.command_argv` wraps the
same argv as a one-command plan for compatibility with expert next-action
consumers. A human-readable command is display-only.

The argv preserves the requested verb and material options: explicit local or
plan selection, sync `--all`, fresh/deep context, compile/stage/apply flags,
recall embedding model and preference evidence, route-gaps top/budget settings,
and output/confirmation flags. Selected capacity and model identifiers are
recorded separately because automatic selection and profile-local models are
runtime decisions, not command-line arguments. Retry guidance must never invent
a metered fallback or omit an explicit-local request.

## Observation contract

`LocalCapacityObservation` is a versioned read-only payload with one of three
states:

- `free`: a supported probe returned valid utilization samples below the busy
  threshold.
- `busy`: at least one supported GPU returned utilization at or above the busy
  threshold.
- `unknown`: the probe tool is absent, timed out, failed, or returned malformed
  output.

The initial NVIDIA adapter invokes `nvidia-smi` with argument-safe argv and a
short timeout, querying GPU utilization only. It may report resident VRAM for
operator context later, but resident memory is not a busy verdict. Ollama keeps
model weights loaded between calls, so treating allocated VRAM as contention
would cause a scheduled loop to block itself.

The probe is portable by degradation: systems without `nvidia-smi`, including
non-NVIDIA systems, report `unknown`. Unknown is visible but does not block
dispatch. This avoids claiming a GPU is free without evidence while preserving
scheduled local work on platforms for which Deepr has no occupancy adapter yet.

The default busy threshold is 35 percent GPU utilization. It is a flow-control
threshold, not a semantic verdict. Probe execution and time are injectable in
tests.

## Durable wait and adaptive retry

A confirmed busy observation records:

- `status: waiting`
- `stop_reason: capacity_unavailable`
- `capacity_unavailable_reason: local_gpu_busy`
- the full local-capacity observation
- `retry_after_seconds`
- `retry_at` as an absolute UTC timestamp
- `requested_operation.command_argv` plus selected capacity/model metadata

Retry delay is derived from consecutive scheduled local-busy waits for the same
expert and loop type:

1. first busy wait: 30 minutes
2. second busy wait: 2 hours
3. third and later busy waits: 6 hours

Any intervening non-busy loop outcome resets the sequence. The current process
does not sleep or spin. The host scheduler or caller uses `retry_at` as guidance.
This preserves catch-up scheduling while bounding delay at six hours.

For sync-all, one waiting run is appended for each expert in the selected roster
that has subscription work because loop-run storage and fleet status are
expert-scoped. Experts with no selected subscription targets are not falsely
marked as capacity-blocked. All rows share the same occupancy observation and
observation time, while each expert derives its own consecutive-wait count.

## Capacity visibility

`deepr capacity` and `deepr capacity next` expose the same observation payload.
Human output labels local GPU capacity as `free`, `busy`, or `unknown`. Busy
next-action guidance tells scheduled work to retry rather than advertising the
local rung as immediately ready. Unknown output states that scheduling will
continue because no supported contention signal was available.

## Failure and safety behavior

- Probe errors never become maintenance failures.
- Busy is normal waiting state, not failed work.
- No process termination, GPU reset, priority change, or long in-process wait.
- No provider, plan CLI, model, or paid API call is made by the occupancy probe.
- No busy local rung silently widens into another capacity source.
- Existing admission and measured-quality gates remain authoritative before
  local capacity can be automatically selected.

## Alternatives rejected

- VRAM-used threshold: rejects an idle Ollama model that is intentionally kept
  resident and makes the loop self-blocking.
- Treat unknown as busy: disables scheduled local work on AMD, Apple, CPU-only,
  and NVIDIA installations where the utility is not on `PATH`.
- Fall through to plan or API when busy: violates no-surprise-bills and changes
  a temporary owned-hardware wait into an unrelated capacity decision.
- Sleep and poll in the command: holds a process and overlap lock for hours,
  hides state from the durable loop record, and duplicates the host scheduler.

## Follow-on work

Add tested occupancy adapters for other platforms only when they expose a
stable read-only signal. Extend the same shared gate to another scheduled local
surface after sync and sync-all telemetry shows that the state classification
and retry cadence are useful.
