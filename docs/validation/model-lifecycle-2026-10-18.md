# Model lifecycle correction, 2026-10-18

Scope: #231 and #217, under the
[lifecycle presentation design](../design/model-lifecycle-presentation.md).
This is inspection and compatibility evidence, not model-quality or account
eligibility validation. No paid provider call was made.

The released v2.50.32 source reproduced nine defects: six finite CLI choices
advertised shut-down deep-research IDs, and three stable Gemini 2.5 contracts
conflated prior-user access with deprecation. The same probe reports zero
defects against the candidate. Historical explicit IDs and pricing survive.

Focused checks cover 116 cases across research refusals and the new lifecycle
regressions. Explicit Gemini price previews retain the selected model and show
unverified access in JSON; normal dispatch still refuses that contract before
a provider call. Unknown IDs remain invalid. GPT-5 alias notices do not
silently migrate explicit selections or match unrelated family names.

The initial integrated run exposed one output regression after 3,693 passes:
an environment-selected retired ID printed a notice to stderr during a JSON
execution refusal. The existing machine-refusal contract was restored and the
116-case rerun passed. That interrupted run and its failure remain retained;
it is not full-suite acceptance. Full unit coverage, independent coverage
enforcement and exact-head CI remain required release gates.

Frontend checks used CI's Node 24.18.0 and npm 12.0.1. Lint, unit tests and
production build passed. The isolated browser fixture passed 102 checks over
light/dark themes and 320, 390 and 1440 pixel widths. Its prior-user contract
is absent from selectable model cards while the available fixture remains.
Light mobile and dark desktop screenshots were visually inspected. The
fixture contacted no backend or provider.

Strict typing passed for 291 files. The wider tree has the same 196 baseline
errors in 60 files, with no added normalized errors. Package checks passed
57 cases; clean-wheel plugin checks exercised MCP 2025-06-18 and 2026-07-28,
the host profile and package replacement persistence. Final artifact and
public-installer validation remain separate publication checks.

Logs, probes, failed trials and screenshots are retained in the existing
ignored `.agent/reader-evidence/` directory. No codegraph was available; callers
and tests were traced directly from source. The original S0 inputs remain
unrecovered, and this repair does not advance an expertise-quality gate.
