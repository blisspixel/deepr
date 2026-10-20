# Absorption deduplication admission, 2026-10-20

Scope: #271. This repairs destructive report-absorption merge admission. It
qualifies write behavior with synthetic verdicts, not semantic judge accuracy.
No inference, paid request, credential change or canonical expert mutation was
part of the reproduction or tests.

## Failure reproduced

On main `7f531c286fe824e247943014b7eaed35b71ceed1`, an offline probe changed
10 USD to 30 USD in a 17-word synthetic pricing claim. Word overlap was
0.941176, so no deduplication verdict was requested. The new claim replaced the
old one. A second price/unit change with 0.818182 overlap obtained no verdict
and also replaced the prior claim. Both went through the real staged commit
boundary and temporary belief stores.

The first regression set produced ten failures and one pass against that
source. The retained log distinguishes data-loss assertions from missing new
pair-binding fields. A later isolated test launch initially resolved the
installed original checkout; explicit `PYTHONPATH` selected the repair worktree
and its module path was verified. That mistaken launch is not candidate
validation. Logs and the reproduction receipt remain under
`.agent/replacement-rehearsal-2026-10-20/`.

## Resulting behavior

Every routed absorption merge now needs an exactly parsed SAME verdict. A
near-identical statement still requires that verdict. DIFFERENT, malformed or
unavailable verdicts, and disabled verification, preserve separate claims and
leave prior confidence and provenance intact. Existing dynamic cost admission
continues to bound every verification call and abort staging before writes.

Before awaiting the verdict, the staged mutation snapshots the candidate
claim/domain and target id/text. The commit holds the existing mutation lock,
reloads concurrent changes and checks the actual merge target. Changed,
removed or different targets and changed candidate text cause separate
insertion. Earlier staged ids resolve through the existing committed-id map;
that mapping cannot authorize changed target text.

The focused tests cover both overlap ranges, valid SAME, unknown/malformed
replies, synthetic transport failure, disabled verification with no verdict
call, retained provenance/confidence, independently written changes and
archives, two live neighbors, changed candidates and staged-target resolution.
The CLI, MCP, knowledge-absorption and parent-budget callers are also exercised.

## Verification

The core offline suite passed **13,585 tests with 22 skipped** in 1,816.17
seconds. Combined statement/branch coverage was **85.68%**; the independent
coverage report also passed the configured gate. This full run preceded the
final CLI wording-only correction: a separate regression first failed because
the CLI called unknown equivalence a false merge. After the correction,
**262 CLI and core tests passed** on the final source. Exact-head CI must
validate the complete patch before merge; use
[the issue verification record](https://github.com/blisspixel/deepr/issues/271#issuecomment-6294813740)
for head and resulting-main checks.

The 296-file strict type gate passes. The wider expert-package baseline has
the same 95 existing diagnostics, including the same 61 distinct messages,
after normalizing line locations, with no additions or removals. Lint,
formatting, file-size and complexity/security ratchets, paid-API boundaries
and doc consistency pass without weakening any gate. Blocked merge counts
describe admission outcomes and do not assert that unknown claims differ.

Two full-suite launches encountered exhausted `/tmp` inodes, not disk-byte
capacity. Their logs remain evidence of environment failure, not assertion
acceptance. The first was also interrupted before the final candidate-binding
change. The final launch uses an absolute task-local `TMPDIR` on the repository
filesystem, retaining the standard offline suite, socket guard and coverage
gate. No unrelated temporary files were removed.

## Limits

This protects future report absorption. It cannot reconstruct claims or
provenance already lost to a historical merge. The lexical router may miss
paraphrases; an explicit SAME verdict may itself be wrong. No calibrated
semantic accuracy, better advice, automatic default promotion or S0 acceptance
is established. Generic operator-directed and shared belief-store merge APIs
remain outside this bounded repair. The design and rejected alternatives are
in [the admission contract](../design/absorption-dedup-admission.md).
