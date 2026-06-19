# Local Working Skills

This file captures repo-specific operating lessons from autonomous work cycles.

## Capacity QOL Work

- Treat capacity planning as deterministic workflow state. It can inspect local ledgers, admissions, model availability, and command shape, but it must not make semantic quality claims beyond measured numeric floors.
- `deepr capacity next` is a read-only `$0` surface. It may suggest commands, waits, setup, probes, evals, admission, or explicit metered fallback. It must not run research, probe paid APIs, write quota observations, or spend.
- Fresh/deep local sync context is a local-capacity contract. If local capacity is blocked, the safe scheduled action is to wait or unblock local capacity, not silently fall through to metered API.
- Scheduler-facing CLI work should consume the same deterministic capacity preview object that `deepr capacity next` prints. That keeps human guidance and automation behavior aligned, and makes blocked recurring jobs an explicit wait state instead of an error or surprise spend.
- When a recurring maintenance surface has no cheap execution backend yet, do not fake readiness through the capacity preview. Return a structured wait with pending work and make the operator rerun without `--scheduled` if they intentionally want the metered path.
