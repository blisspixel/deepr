# Research and compatibility verification

Status: v2.50.15 patch verification, September 13, 2026. These are software
compatibility and safety checks, not a completed expert-value pilot. The
[matching release](https://github.com/blisspixel/deepr/releases/tag/v2.50.15)
records its exact published commit, final hosted CI run, and artifact hashes.

## Scope

- Claude production plan refusal for unconfined managed-policy hooks, including
  explicit selection and quota-observed automatic routing.
- MCP legacy ping and malformed-message handling, retaining the published
  `2026-07-28` contract and documented `2025-06-18`, `2025-03-26`, and
  `2024-11-05` legacy revisions.
- Agent Plugins `1.0.0` metadata, single-pass placeholders, contained relative
  working directories, and the existing read-only package. Version `1.1.0`
  remains a draft and is not advertised as supported.
- README, roadmap, capacity guidance, the cited evidence assessment, and
  surgical refinement of the existing shared AGENTS guide.

## Completed focused checks

| Check | Observed result | Limit |
| --- | --- | --- |
| Claude adapter, safety, client, fleet, waterfall, and capacity tests | 256 passed | Offline injected transports; no live provider or account check |
| Agent Plugin package and launch regressions | 31 passed, zero skipped; new cases first reproduced 11 failures | Synthetic executables were resolved but not run |
| Standards pins and portable Agent Skills contract | 11 passed, zero skipped | Does not certify an external host |
| Final MCP envelope, dispatch, and modern HTTP regressions | 112 passed | Shared shape validation and protocol-era behavior, not host certification |
| Independently found HTTP notification admission defect | 104 passed in the focused HTTP set; new cases first reproduced 11 failures | Authentication retained; notifications do not enter tool admission, accounting, or dispatch |
| Production capacity CLI refusal | 50 cases passed; both changed sync-all cases passed | Broader combined run encountered the Windows initialization hang below |
| Upstream schema comparison | Published Agent Plugins schemas and pinned MCP schema match stored digests | Read-only upstream files, not a runtime interoperability result |
| v2.50.15 clean core wheel and installed Windows stdio | Passed both 2025-06-18 and 2026-07-28 exchanges; exactly ten read-only tools; blocked research; expert data preserved across package replacement | Isolated fixture state, no external client certification |
| Deterministic Agent Plugin archives | Both builds SHA-256 `6ce97d33bac28eb0604acbecaf2f48df716b2eaf1d4c8a92e6734bb7742011af` | Package bytes, not semantic quality |

Focused sets overlap and must not be summed into a unique full-suite count.

Windows full-suite attempts timed out in Proactor initialization at
`socket.socketpair()` / `lsock.accept()` before test bodies. Bounded diagnostic
subprocesses reproduced the path on Python 3.12.13, 3.13.15, and 3.14.7 with
the localhost socket allowlist; ordinary loopback connection probes also
failed intermittently and later recovered. This does not establish port
exhaustion or a product-level fix. The installed v2.50.15 smoke subsequently
completed on Windows with its external deadline retained. No event-loop
replacement, disabled socket guard, or skipped regression was introduced.
The remaining healthy-host Windows full-suite check is in the roadmap.

## Final gates

Ruff lint and formatting, strict mypy across 162 source files, both code-health
ratchets, paid-API boundary checks, and documentation consistency pass. The
dependency audit reports no known vulnerabilities. The wider non-blocking
mypy run reports 193 errors in 61 files; it is not strict-clean, and no new
ignore or gate exception was added. None of those diagnostics names a changed
production module. Changed Markdown links and added writing characters were
checked. Git author/coauthor history, current contributor entries, and the
repository authorship-credit scan contain no Codex or Claude attribution.

Full no-key unit coverage and exact-change CI are mandatory publication gates.
The CI workflow runs Python 3.12, 3.13, and 3.14, enforces the configured
coverage result separately, and runs package installation, frontend, security,
lint, and strict-type checks. The 80 percent minimum is coverage.py's combined
statement/branch score with branch measurement enabled. The release must name
its successful exact-commit CI run; neither focused tests nor an older green
run substitutes for it. No lower threshold, xfail, disabled socket protection,
or metered test is authorized.

The initial `main` revision, `9054231512aa359825e19c2a0b385b4b4e4c95d9`, had a
[successful hosted CI run](https://github.com/blisspixel/deepr/actions/runs/34381153525).
That result covers the starting revision, not these working-tree changes.

## Capacity and claim boundary

No Deepr paid inference, embedding, account-control request, plan execution,
or cloud deployment was performed for this work. Test fixtures and install
checks use isolated local state. The $10 effort ceiling does not revise the
repository's no-paid-API rule or its $5 maximum for active examples. Conversation
and delegated-agent billing is not exposed by the application ledger; no
all-inclusive dollar-total claim is made.

No blinded answers, semantic reviewer attestations, or expert-value result
were generated. The next experiment still needs the reviewed inputs and
independent semantic review described in the
[evidence assessment](../research/deepr-next-evidence-2026-09-13.md).
