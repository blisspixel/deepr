# Plan-quota CLI backends

Status: implemented safety boundary, updated 2026-07-18. Implements the ROADMAP
Phase 6 "CLI provider adapters" rung of the capacity waterfall
([capacity-waterfall.md](capacity-waterfall.md)). Governs how Deepr drives a
vendor's own coding/agent CLI as a research backend without producing a surprise
bill. Read [AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) first - this is a
textbook "determinism on the money side-effect, model judgment on meaning"
surface.

## The bet, and the honesty test

Phase 6's promise is "your existing subscriptions become research capacity": a
flat monthly plan you already pay for runs Deepr's non-urgent, batchable
maintenance and expert bootstrapping (`expert sync`, `expert absorb`, topic
`expert learn`, `learn-web`, gap-fill, health-check) at **$0 at the margin**, before any metered
API dollar. That promise only holds for a CLI where the marginal request inside
the plan window is genuinely free. So every candidate CLI is run through one
test:

> Is the next headless call free at the margin on a flat subscription, or does it
> bill per use?

A CLI that bills per use is just the metered API wearing a CLI costume - it earns
no place as "free capacity". The June-2026 survey:

| CLI | Headless cmd | $0 at margin on a flat plan? | Auto-routable | Why |
|---|---|---|---|---|
| Codex (`codex exec`) | yes | yes, within 5h/weekly window | no, blocked | Native read and shell tools cannot be disabled or narrowly confined for an untrusted prompt. |
| Claude Code (`claude -p`) | yes | yes only while paid extra usage is explicitly off | **yes** | Each dispatch proves the provider-reported overage switch is off, then uses safe mode with empty tool and MCP surfaces, no persistence, the included `sonnet` alias, and no API credential. |
| OpenCode (`opencode run`) | yes | only if routed to an OAuth/local provider | no, blocked | Provider identity, stored credential type, marginal cost, and native tools cannot be proven before dispatch. |
| Kiro (`kiro-cli chat`) | yes | only with prepaid auth and overage off | no, blocked | Read tools are not narrowly confined and prepaid overage posture is unproven. |
| Grok Build (`grok -p`) | yes | subscription quota, but gray | no, blocked | Native tool permissions cannot be disabled or confined for an untrusted prompt. |
| Antigravity (`agy -p`) | yes (answer read from transcript, not stdout) | weekly hard-stop | no, blocked | Native tool permissions and transcript side effects cannot be disabled or confined for an untrusted prompt. Headless policy risk also remains. |
| Copilot (`copilot -p`) | yes | **no** - usage-based since 2026-06-01 | no, blocked | Complete metered estimate, reserve, settle, and ledger support is absent. |

"Auto-routable" means Deepr's waterfall may *automatically* select it after
admission and a trusted remaining-quota observation. An explicit `--plan <id>`
selects an adapter but never bypasses the safety decision. Claude is the only
current auto-routable adapter. Every actual Claude dispatch repeats the live
paid-overage check immediately before process construction. Every other adapter
remains detectable for honest fleet visibility but fails before process
construction.

Claude's execution argv is deliberately narrower than ordinary Claude Code:

```text
claude --safe-mode --tools "" --no-session-persistence --disable-slash-commands --strict-mcp-config --mcp-config '{"mcpServers":{}}' --model sonnet -p -
```

The prompt is delivered on stdin. `--safe-mode` suppresses ambient hooks,
skills, plugins, memory, and project instructions while preserving stored plan
authentication. `--tools ""` removes built-in tools, and strict empty MCP
configuration prevents ambient servers. The live metadata observation is
durably written before the model call; an unavailable response, an unknown
field, enabled extra usage, or a ledger failure stops the call. Claude Code
2.1.206 refuses a zero `--max-budget-usd`, and a positive value would authorize
a dollar amount, so Deepr does not present that flag as a zero-bill control.

This posture supersedes earlier live transport validation in this document. A
CLI successfully returning text proves transport compatibility, not safe
execution for untrusted research prompts and not vendor billing treatment.

## Two seams, one chosen

Deepr has two execution seams. The heavy `DeepResearchProvider` contract
(submit/poll/vector-stores) is API-shaped and wrong for a subprocess CLI. The
light `research_fn` seam - `(query, budget) -> {"answer", "cost", ...}`, the same
one the local Ollama backend uses - is exactly right and is what the flagship
payoff (scheduled expert maintenance) flows through.

`expert sync` and topic `expert learn` both perform model synthesis and verified
belief extraction. A CLI is not an OpenAI client, so to run the **whole** run on
prepaid capacity (no silent metered extraction) the adapter is exposed as a
`PlanQuotaChatClient`: it satisfies the minimal
`client.chat.completions.create(model=, messages=) ->
.choices[0].message.content` surface every Deepr chat seam already uses, exactly
like `ollama_chat_client`. One client instance serves synthesis and the
`ReportAbsorber`, so the entire loop runs on the plan. The same client backs the
multi-expert **consult** synthesis seam (`ExpertCouncil`), so an external agent
can run a whole fan-out consult on prepaid capacity.

**Prompt delivery is over stdin, not argv where the adapter supports it.** A multi-line prompt (a synthesis
prompt with several experts' perspectives, a long report) passed as a
command-line argument to a `.cmd` shim is mangled by `cmd.exe` on Windows: the
child sees an empty task and answers conversationally at $0 - a silent quality
failure, not an error. Codex and Claude declare `stdin_prompt=True`; only Claude
currently passes the complete execution gate. Any future plan adapter
that may receive long or multi-line prompts should do the same.

## Bounded subprocess output

Every plan adapter uses one shared process runner. Each invocation drains stdout
and stderr concurrently and retains at most 8 MiB from either stream. The
ceiling is measured on raw bytes before UTF-8 decoding, so multibyte text cannot
expand or bypass it. Reaching the ceiling is not enough to stop a process;
crossing it produces the typed dispatched outcome `output_limit_exceeded`,
requests bounded termination and reaping of the whole process tree, and never
retries or switches backend. Unconfirmed cleanup takes precedence as a typed
cleanup failure.

An overflow is ambiguous quota usage. The client and probe paths therefore
record one `ATTEMPT_OBSERVED` quota event with unknown units and one matching
`$0` canonical cost event under the same attempt id. A launch that never enters
the dispatch boundary retains the existing no-quota-observation behavior.
Captured output remains bounded and is not promoted as an answer after
overflow.

Process-tree ownership is established before vendor code can run. On Windows,
the child starts suspended, enters a
[kill-on-close Job Object](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
and only then resumes, so a descendant remains owned even when the direct child
exits first. Cleanup explicitly terminates the Job Object before closing its
  handle with bounded retries; a failed termination or close becomes a typed
  cleanup failure instead of promoting an answer under uncertain ownership. A
  failed close retains the handle in a process-global retry registry, and later
  launches fail closed until that owner can terminate and close the job. Cleanup
  uses stable process and Job Object handles rather than PID-based `taskkill`, so
  an asynchronously reused root PID cannot be targeted. On
Linux, a child-subreaper supervisor adopts and terminates descendants that
create a detached session. A parent-only status pipe distinguishes vendor launch,
runtime, and cleanup outcomes from vendor-controlled stdout and stderr. Child
enumeration failure and a forced supervisor kill fail closed as cleanup errors.
  Other POSIX systems fail before process launch because a process group cannot
  contain a deliberately re-sessioned descendant. Support requires an equivalent
  pre-execution ownership primitive rather than a documented escape. If Windows
  ownership setup fails, Deepr terminates the suspended child and reports a launch
failure before prompt delivery or vendor dispatch. Overflow readers keep
draining and discarding beyond the retained ceiling until cleanup closes the
pipes; bounded cleanup waits for process exit without re-entering
`Process.communicate()` and always closes the subprocess transport if an
inherited pipe does not reach EOF.

The runner cannot use `Process.communicate()` for this path because the
[Python asyncio subprocess contract](https://docs.python.org/3/library/asyncio-subprocess.html#asyncio.subprocess.Process.communicate)
buffers returned data in memory and warns against large or unlimited output.
Sequential pipe reads are also unsafe because the unread pipe can fill and
deadlock the child. The accepted implementation writes stdin while draining
both output streams concurrently, keeps timeout and cancellation ownership,
  applies one elapsed deadline across subprocess launch and execution, and performs
  bounded process-tree cleanup on every terminal path. A launch still pending
  after the bounded grace period remains under a tracked cleanup task, while the
  timeout or cancellation carries explicit unconfirmed-cleanup state. This is deterministic
resource and side-effect enforcement, not a judgment about answer quality.

## The deterministic safety gate (no-surprise-bills)

Money side-effects are gated deterministically; nothing here judges answer
quality. Before any subprocess runs (`safety.evaluate_plan_quota_safety`):

1. **Child auth mode must be plan, not a metered API key.** If a backend's
   metered-env var is set (`OPENAI_API_KEY`/`CODEX_API_KEY` for codex,
   `ANTHROPIC_API_KEY` for claude, `XAI_API_KEY` for grok, ...), a normal CLI
   launch could bill that key on vendor precedence rules. Deepr therefore
   removes those known metered vars from the child environment first, records
   that sanitization in the safety reason, and evaluates the sanitized child
   env as the plan path. (`codex doctor` / `codex login status` can confirm the
   stored mode too, but the child env is the deterministic launch contract.)
2. **A metered-at-margin CLI requires complete cost accounting.** Copilot is
   `metered_at_margin=True`. A confirmation cannot enforce a ceiling or make a
   `$0` ledger event truthful, so the safety decision rejects it before probe,
   client, provider, or subprocess construction. It remains blocked until the
   adapter has a deterministic maximum estimate, durable reservation, reported
   usage settlement, and canonical cost-ledger writes. Existing backend choices
   and acknowledgement flags remain accepted for compatibility but cannot
   override this guard.

Every eligible non-metered dispatch also writes the append-only ledgers, whether
the CLI succeeds, exits nonzero, times out, or returns no answer. The canonical
`$0` cost event records the bounded outcome plus whether vendor dispatch and
quota usage were observed. The quota ledger distinguishes known facts: success
is `USAGE_OBSERVED`, a depletion signature is terminal `EXHAUSTED`, and an
ambiguous nonzero, timeout, or empty-output result is `ATTEMPT_OBSERVED` with
usage left unknown. A process that never launched writes no quota observation.
Probe helpers own this accounting directly, so CLI wrappers do not duplicate a
successful event. This keeps `costs show`, fleet state, and anomaly detection
honest without inventing a used quota unit.

Failure diagnostics use a bounded, credential-redacted tail of stderr. This
preserves the terminal vendor cause after long banners and progress streams,
while prompt-overlap filtering prevents an echoed research prompt from crossing
the error boundary. Stdout is never used as a public nonzero-exit diagnostic
because it may contain model output or source material. Vendor limit wording
that could occur in ordinary answer text is registered as error-channel-only;
Codex's current `You've hit your usage limit` phrase is classified only from
stderr.

## Auto-routing requires intent and quota evidence

Vendor CLI execution commands generally do not expose trustworthy *remaining*
quota, so Deepr never auto-routes on a guess. An explicit, dated admission is
still useful, but it records operator intent only. It does not replace the
remaining-quota gate:

- `deepr capacity admit-plan claude --task-class sync` (also `absorb` and
  `gap_fill`; paired with `revoke-plan`) records a plan admission in the shared
  admission store, namespaced `plan:<id>` so the local rung never mistakes it
  for an Ollama model. Only a genuinely free-at-margin, ToS-clean adapter that
  also clears the native-tool and auth-provenance gate can be admitted. Claude
  is the only current candidate.

The waterfall's plan-quota rung (`choose_maintenance_backend` ->
`_choose_plan_quota`) auto-selects a CLI only when it is installed, in plan auth
mode, admitted for the task class, **and has a trusted remaining-quota
observation** in the local quota ledger. A backend seen `EXHAUSTED` with a
future `reset_at` is skipped. Once the reset passes, the exhaustion no longer
blocks it, but a fresh trusted remaining-quota observation is still required
before auto-routing resumes. A future fully accounted metered rung is the
budget-gated last resort; v2.36 stops rather than falling through to it.

The explicit path needs no admission (the operator chose it directly), but it
still requires a non-metered adapter that clears the safety gate:

- `deepr expert sync NAME --plan claude` (also `absorb`, topic `learn`, `learn-web`,
  `route-gaps --execute`).
- `deepr expert sync-all --plan claude` - run a whole roster pass through one
  non-metered plan backend. The automatic `sync-all --scheduled` path consumes
  a plan backend only when `choose_maintenance_backend` returns an admitted,
  quota-observed plan choice; it does not infer quota from CLI presence.
- `deepr expert route-gaps NAME --execute --scheduled` - scheduled gap-fill
  uses the `gap_fill` task class and consumes an admitted, quota-observed plan
  choice from the same selector before it runs. Otherwise it waits instead of
  spending on metered research.
- `deepr capacity probe-plan claude` - validate auth + one round-trip.
- `deepr capacity probe-fleet --backend codex --backend claude` - inspect
  several selected backends concurrently, record the same usage/exhaustion
  observations for adapters that dispatch, preserve pre-dispatch refusals for
  blocked adapters, and emit a versioned
  `deepr-plan-fleet-probe-v1` payload. This is validation fan-out, not
  auto-routing permission.
- `deepr capacity validate-fleet --backend claude` - run the
  transport probe and no-metered consult contract as one operator health check,
  emit `deepr-plan-fleet-validation-v1`, and fail selected backends that are
  skipped, missing, exhausted, timed out, or return failed synthesis status.
  This is still validation fan-out, not auto-routing permission or semantic
  answer scoring.
- `deepr mcp validate-consult-fleet --plan claude` - run the
  no-metered consult contract through selected plan CLIs concurrently and emit
  `deepr-mcp-consult-fleet-validation-v1`. This proves consult envelope,
  capacity, trace, cost, and collaboration metadata across multiple backends;
  it still does not score answer meaning.

`choose_plan_quota_backend` resolves an explicit `--plan` request through the
same safety gate but without the admission/observed-quota requirement. Its
legacy metered-acknowledgement argument cannot override missing cost accounting.

## Fleet visibility

`deepr capacity fleet` (builder: `fleet.build_fleet_status`) shows every
plan-quota CLI in one read-only `$0` table: installed (PATH), effective child
auth mode after metered env vars are removed, raw parent-shell auth mode for
diagnostics, routability (auto / explicit / metered), and the latest *observed*
quota state (active / attempt_failed / exhausted / quarantined / unobserved)
with a reset time when one was parsed from the vendor's exhaustion message or
from a metadata refresh. `attempt_failed` means dispatch was observed but quota
use remains unknown. "unobserved" and a blank reset are deliberate: Deepr
reports only what it has seen, never a fabricated remaining-quota number. Reset
times are recorded on `EXHAUSTED` events from either a relative duration
(`Try again in 3h 42m`, `Resets in 2h15m30s`) or a host-local Codex clock
(`Try again at 9:20 AM`). Absolute clocks use the operating system's local
timezone and DST rules, roll to tomorrow only when today's unique instant has
passed, and convert to UTC. Ambiguous fall-back clocks, nonexistent
spring-forward clocks, and unavailable conversion stay honestly unknown rather
than guessing an offset. This is deterministic form extraction, never a
semantic verdict. Monthly pools with no countdown also stay unknown. Codex
supports proactive metadata refresh:
`deepr capacity refresh-quota codex` reads local session-log `rate_limits`.
Claude Code supports
`deepr capacity refresh-quota claude`, which reads the current user's Claude
Code OAuth usage metadata from the read-only usage endpoint when credentials
are present. Grok supports `deepr capacity refresh-quota grok`, which reads the
current user's Grok CLI auth file and calls the Grok billing metadata endpoint
to parse a monthly gRPC-web quota frame. These refreshes normalize the binding
window through `QuotaSnapshot` and write `VENDOR_REPORTED` ledger events
without running a model call. Published as the versioned
`deepr-plan-fleet-v1` envelope.

`deepr capacity probe-fleet` is the active validation surface: it makes tiny
parallel `Reply with exactly: OK` calls to selected non-metered plan CLIs,
records quota-ledger observations, and fails if selected backends fail or
nothing actually ran. Metered-at-margin selections return a failed result
before probe dispatch. `--include-metered` and `-y` remain parseable for
backward compatibility but cannot authorize execution. The command is
intentionally separate from auto-routing because most CLIs still do not expose
trusted remaining quota.

`deepr capacity validate-fleet` is the defensive operator validation surface:
it runs the transport probe first, then consult-contract validation only for
backends whose transport succeeded. Its wrapper timeout is longer than the
plan-subprocess timeout so typed backend failures can surface, and its report
keeps transport status, consult status, synthesis status, skipped backends, and
failed backends separate.

`deepr mcp validate-consult-fleet` is the contract validation companion. It
fans out in-process `deepr_consult_experts` calls over selected plan backends,
preserves the no-metered fallback invariant, and reports one result per plan.
It is intentionally side-effect and form validation, not a semantic ranking of
which CLI answered best.

## What is deterministic vs model judgment (AGENTIC_BALANCE)

| Concern | Setting |
|---|---|
| auth-mode detection, metered-adapter cost-lifecycle gate, exhaustion and attempt-outcome accounting, redacted tail diagnostics, quota+cost ledger writes, argv construction, tool lockdown (`--deny-tool`/read-only sandbox), scratch cwd | **workflow** (deterministic, gated) |
| the research answer and the extracted beliefs | **agent** (model), then through the existing absorb gates: confidence floor, source-trust ceiling (research-derived = tertiary, capped), contradiction + dedup verdicts |

The plan CLI is an answer generator on the cheap-capacity side of the waterfall;
every claim it produces still passes the same verification gates as any other
source. The trust-floor ceiling means even an imperfect extraction cannot mint a
high-confidence belief.

## Known follow-ups

- Live quota probes that record a *trusted remaining* signal let the
  auto-routing rung light up only when the candidate backend has observed
  headroom. The shared snapshot contract exists, and Codex, Claude Code, and
  Grok now write `VENDOR_REPORTED` ledger events from metadata-only
  refreshes. Next probe: Antigravity as explicit-only metadata visibility.
- `deepr capacity` detection ids are exe-based (`kiro-cli`, `agy`) while
  execution ids are canonical (`kiro`, `antigravity`); the capacity quota display
  for those two does not yet join to execution-recorded usage. Cosmetic.
- Prompt delivery is declared per adapter: `prompt_is_file` (Grok `--prompt-file`),
  `stdin_prompt` (Codex `codex exec -`, Claude `claude -p -`), or a plain argv
  (short-prompt CLIs). `client._build_invocation` resolves the mode, writes a
  temp file for file-mode and removes it after the run, and both `_run_chat` and
  the probe share it. Transport-only validation on a Windows build 2026-06-25
  showed Codex, Claude, and Grok returning long research/synthesis prompts (Grok
  previously failed with WinError 206 - the prompt exceeded the command-line
  length limit - until it was moved to `--prompt-file`).
- Antigravity drops stdout under a non-TTY pipe (confirmed v1.0.12: `agy -p`
  exits 0 with empty stdout when piped); the fix is not a flag. It now works
  headless by recovering the answer from antigravity's own transcript
  (`~/.gemini/antigravity-cli/brain/<conv-id>/.system_generated/logs/transcript.jsonl`):
  each line is a JSON record, and the reply is the last `PLANNER_RESPONSE` after
  the current invocation's exact `USER_INPUT`. Every attempt appends a unique
  nonce to its prompt so another Deepr process or external invocation cannot
  produce the same correlation identity. Dispatch and recovery hold one
  cross-process lock. The client accepts only a transcript changed from a
  pre-dispatch snapshot and, for an existing JSONL file, only an exact prompt
  appended after its baseline byte offset. Unrelated newer conversations cannot
  supply the answer. The pre-dispatch snapshot runs off the event loop within the
  elapsed dispatch deadline. Root-directory enumeration, changed candidates,
  actual bytes read, decoded answers, and lazy JSONL line iteration are bounded;
  the whole recovery shares one 8 MiB operation ceiling. Overflow remains
  `output_limit_exceeded` with unknown quota usage. Lock-release uncertainty is
  typed without masking the primary outcome. The adapter sets
  `answer_from_transcript=True` and the client uses this invocation-correlated
  result instead of stdout.
  Validated end to end 2026-06-25: `probe_plan_quota(antigravity)` returned the
  expected reply in ~5.5s on plan auth. Antigravity stays explicit-only and ToS
  gray-zone (active ban wave) despite working. Grok transport was previously
  validated, but current execution is blocked and its policy remains gray. A ConPTY wrapper remains a possible alternative if
  the transcript path ever changes.
- OpenCode is BYO-provider and now fails closed as `unknown` before dispatch. A
  future adapter needs a trustworthy per-run provider identity, stored
  credential classification, marginal-cost proof, and native-tool confinement
  before execution can return.
