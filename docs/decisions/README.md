# Architecture Decision Records (ADRs)

Short, append-only records of decisions that are expensive to reverse or
easy to forget the reasoning behind: a chosen contract, a rejected
alternative, a trade-off taken on purpose.

**Why these exist.** Commit messages explain *what changed*; the roadmap
tracks *what is planned*; design docs (`docs/design/`) explore *how a large
feature should work*. An ADR captures *why a decision went the way it did* -
the option space, what was chosen, and what was deliberately not. For a
spare-time project maintained across machines and long gaps, that durable
rationale is what stops a future session from re-litigating settled calls
or silently undoing them.

**Weight.** Keep them to a page. Write one only when a decision is
cross-cutting, hard to reverse, or surprising enough that "why did we do it
this way?" will be asked later. Most changes need no ADR. This is not a
gate; it is a memory aid.

## How to add one

1. Copy `template.md` to `NNNN-short-title.md` (next number, zero-padded).
2. Fill it in. Status starts `Accepted` (or `Proposed` if seeking review).
3. Link it from the relevant ROADMAP item or design doc when useful.
4. ADRs are immutable once accepted. To change a decision, write a new ADR
   that supersedes the old one (and mark the old one `Superseded by NNNN`).

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-one-reports-root-from-config.md) | One reports root, sourced from config | Accepted |
| [0002](0002-agent-error-envelope-on-every-surface.md) | Agent error envelope on every error surface | Accepted |
| [0003](0003-cli-non-tty-and-self-update.md) | CLI: non-TTY safety and self-update | Accepted |
