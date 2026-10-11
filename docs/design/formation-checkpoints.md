# Durable local formation and measured progress

Issue 203 concerns initial owned-local expert formation that stops before a
whole lens finishes. This change depends on PR 206 at
`57a92b8fafcd347604aa8e783ccef4f200ab1f83`, including its local preflight and
dispatch-time cloud/model proofs. It does not qualify an expert's advice.

## Checkpoint contract

The shared study checkpoint seam owns a versioned manifest and one atomic,
fsync'd record per structurally valid lens/chunk response. The contract field
or an established array alias must contain objects; duplicate JSON keys, error
envelopes, missing fields and scalar/nonobject arrays are rejected both before
completion and when reading old records. The record is saved
before the next model call. A valid empty array is completed work. Failed,
truncated, cancelled, malformed or ambiguously written work is not reusable.
Write failure stops dispatch. Candidate operation directories preserve earlier
attempts; canonical study and brief publication retain their existing gates.

Reuse binds the actual ordered material, including text slices and
prompt-visible source metadata, corpus and chunk limits, lens definitions,
exact assembled prompt, output contract, selected local model and attested
GGUF digest, and native generation options. Records have bounded, strict JSON
validation and content hashes; unknown versions, corruption and stale identity
are reported and excluded. Grounding and merged findings are rebuilt from the
validated response against the current chunk. A legacy lens artifact cannot
prove this identity and is reread once. Checkpoints never provide authority:
present cloud and local-inventory proof is still checked before generation.
The model digest is pinned after preflight and a replacement model is refused
before submission.

On POSIX, completed records opt into the canonical atomic writer's directory
flush: after file fsync and replacement, fsync every ancestor, including new
operation and checkpoint directories. Any flush failure stops the next model
call and removes the ambiguous candidate where possible. This relies on the
host filesystem honoring fsync. Windows uses file fsync and atomic replacement;
portable directory flushing and survival of directory entries after power loss
are not claimed. Process interruption recovery remains available on both.

Completed acquisition has a separate inspectable manifest binding mission,
search plan, query/URL bounds and retained source identity. A matching retry
reuses acquisition instead of silently changing its corpus. Explicit refresh,
changed mission, missing source bytes or changed plan identity prevent reuse.
Source and checkpoint paths are derived from validated identifiers, never
arbitrary paths supplied by records.
The current operation carries bounded, validated checkpoint/acquisition
operation identifiers across refusal or cancellation before study. A candidate
reference advances only after verified records have been copied to the new
operation, so a zero-call retry cannot make earlier completed chunks unreachable.

## Operator controls and progress

`expert make --local` and `expert build` accept `--max-minutes` from 1 through
360, default 45, and an explicit bounded `--max-corpus-chars` option. Validate
these before creating or replacing a profile. The longer time ceiling applies
only to explicit owned-local formation. The 40-model-call ceiling, corpus and
acquisition ceilings, overlap lock, paid/plan quarantine and publication gates
remain. Explicit/profile/previously selected models are pinned. A brand-new
automatic default choice remains available, but a recorded model is never
silently fitted down. No automatic reduction of lenses, chunks or corpus.

After acquisition, report the actual lens/chunk call plan, completed/reused
work, remaining calls and time bound. ETA is unknown without measured timing.
The first real completed chunk is checkpointed and then calibrates progress;
there is no inference probe. Estimates use measured call duration and disclose
sample count and uncertainty. Token throughput is shown only when native
token/evaluation measurements exist. Warnings about likely time or call-limit
exhaustion are advisory, with usable explicit longer-time or smaller-corpus
commands. Hard limits still stop execution and retain completed chunks.
`expert status` adds the current formation operation, progress and estimate
without starting a model or contacting a provider.

Detached CLI execution is deferred. There is no reusable durable process
supervisor; the dashboard's server-owned daemon thread is not overnight CLI
support. Foreground runs can be inspected from another terminal and explicitly
resumed after interruption. This change adds no daemon or background authority.

## Read-only accelerator observation

A shared Linux DRM seam enumerates bounded card devices and reads driver,
vendor and device identity. AMD exposes numeric `gpu_busy_percent` and VRAM
total/used bytes. Keep occupancy distinct from resident memory, and do not
present an iGPU's dedicated VRAM as its complete shared-memory capacity.
Intel i915/xe devices are visible, with unknown utilization when no supported
unprivileged metric is available. Missing NVIDIA support does not imply CPU
execution. No privileged perf collection, sysfs writes or invented process
attribution is introduced.

Connected observation can use Ollama's read-only `/api/ps` to report resident
model identity, memory and GPU residency. It uses the existing owned-loopback
URL validator, bounded timeout, no ambient HTTP credentials/proxies and no
redirects. Offline/skip-connectivity doctor makes no HTTP request. Confirmed
AMD contention follows the existing scheduled-local deferral policy; unknown
observations remain nonblocking and mixed devices are not falsely all free.

The checkpoint, deadline and telemetry rules guard form, persistence and
side-effects. Models continue to own semantic interpretation. Offline
regressions exercise real chunk boundaries, cancellation and write failure,
stale/corrupt identities, model replacement before submission, CLI limits before
profile writes, ETA without probes, and AMD/Intel/unknown diagnostics. No live
inference or hardware completion claim follows from these tests.

Primary interfaces:

- [AMDGPU utilization](https://docs.kernel.org/gpu/amdgpu/thermal.html)
- [AMDGPU VRAM counters](https://docs.kernel.org/gpu/amdgpu/driver-misc.html)
- [Intel perf access](https://docs.kernel.org/gpu/i915.html)
- [Ollama running models](https://docs.ollama.com/api/ps)
- [Linux file and directory fsync](https://man7.org/linux/man-pages/man2/fsync.2.html)
