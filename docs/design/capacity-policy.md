# Capacity policy: free by default, paid by explicit request

Status: operator policy, 2026-08-05.
Implements the posture in [../CAPACITY.md](../CAPACITY.md) at the level of
"which capacity does a command reach for, and when."

## The policy

1. **Default to free.** Local models and prepaid plan quota are the default for
   every expert surface. They cost network and time, not money.
2. **Metered API is a last resort.** It runs only when explicitly requested, with
   an estimated cost shown first, and it is overridable rather than automatic.
3. **Holding a credential is not spending it.** An operator's environment
   legitimately carries API keys for other tools. A key's *presence* must never
   block free capacity.
4. **The safeguard belongs on reachability.** What decides billing is whether a
   dispatch can *read* a metered credential, not whether one exists somewhere.

## Why point 3 mattered enough to change code

The plan-quota gate previously refused Claude Code whenever `ANTHROPIC_API_KEY`
was set anywhere in the environment, on the reasoning that the CLI would
authenticate with it and bill per use. That reasoning is sound in general: the
CLI does prefer the key when it can see one, and says so.

But `plan_quota_child_env()` builds the subprocess environment from an
allowlist that excludes provider credentials, so the child never receives the
key. The gate was inspecting the parent environment while the thing that
determines billing is the child environment.

The practical effect was backwards. An operator who holds a key for unrelated
work was denied the **$0** path and pushed toward the paid one. That protects no
money and costs some.

`detect_auth_mode` now evaluates the child environment, and
`plan_quota_child_env` additionally removes metered variables by name so the
guarantee does not depend on the allowlist staying correct.

### What did not change

- **The gate can still refuse.** If a metered variable can reach the child, auth
  mode is METERED and dispatch is blocked, naming the variable. This is pinned
  by tests that simulate an unfiltered child environment.
- **Unverified stored auth stays UNKNOWN.** Closing the environment path does
  not prove which stored credential a CLI picks up from its own config
  directory. OpenCode and anything else without verified provenance stays
  blocked.
- **Every other adapter stays blocked.** Codex, Grok, Kiro, OpenCode, and
  Antigravity are refused for tool confinement or credential provenance,
  independent of auth mode. In practice this change unblocks **Claude Code
  only**, which is the documented executable plan adapter.
- **Metered dispatch stays frozen.** Nothing here re-enables the paid API.

### The residual risk, stated plainly

`CLAUDE_CONFIG_DIR` and `APPDATA` remain allowlisted because the CLI needs them
to find the subscription session. Stripping the environment proves the
*environment* path is closed; it does not prove that a credential stored in that
config directory is a subscription token rather than an API key. That gap
predates this change and is unaffected by it.

## Applied to the study pass

`deepr expert study` is the highest call-count surface in the expert loop: one
model call per lens over a whole corpus. It therefore has **no `--api` option at
all**. Capacity is local (default) or a non-metered prepaid plan, and an adapter
that bills at the margin is refused with the same reason a metered API would be.

## Being a polite neighbour on shared hardware

Local capacity is free in money and not free in machine. Two rules:

1. **Pin during a run, release after it.** Ollama holds weights warm for a
   keep-alive window so a multi-call workload does not pay a cold reload between
   calls. That is right during the workload and rude afterwards: a 19 GB model
   resident for the rest of the window blocks every other GPU user for work that
   already finished. `expert study` releases the model when the run ends;
   `--keep-warm` opts out.
2. **Say when a model does not fit.** A model whose weights plus context exceed
   available VRAM is placed on CPU, where a study pass takes hours instead of
   minutes. The run stays `$0` and correct and looks like a hang. Deepr now
   reports the split and suggests a smaller model or a shorter corpus budget
   rather than letting the operator guess.
