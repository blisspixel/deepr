# What an expert directory looks like, and why the names changed

Status: built, 2026-08-10. All 57 experts migrated.

## The problem with the old names

Listing an expert directory told you which commands had run:

    study.json  brief.json  positions.json  profile_card.json  practice.json
    viva.json   graph/perspective.json

Every one of those is named after the process that wrote it. That is the
fact-list frame leaking into the filesystem, and it shapes what gets built
next: a file called `positions.json` invites features about positions, and a
directory that reads as a pipeline output invites more pipeline stages.

Two of them were worse than merely process-named.

**`brief.json` and `positions.json` were the same subject twice.** Neither name
says which is the current view and which is the history. A reader had to know.

**`profile.json` and `profile_card.json` were different things sharing a
word.** One is the v1 config record, the other is the expert's own account of
itself. Nothing in either name distinguishes them.

There were also four directories the v1 path created and never used.

## What it looks like now

Every name answers "what is this expert", from the expert's own side:

    self.json      who I am - the name I chose, how I read this subject,
                   my voice, how I want to be depicted
    self.png       the face I chose
    corpus/        what I have read
    noticed/       what I found in it
    hold/
      current.json   what I hold now, which is what a consult reads
      current.md     the readable form of it
      history.json   every view I have held, with what moved it
    became/        the chain of what changed me
    attend/        what I chase, and where I look
    met/           what has been put to me - examinations, consults
    graph/         derived structure: what rests on what

`hold/` is the rename that carries the most. The current view and the history
of views are now visibly the same subject at two time depths, which is what
they always were.

## What deliberately did not move

**`corpus/`.** Already named from the expert's side rather than after a verb,
"corpus" is the accurate word for a body of retained text, and it is a
content-addressed store with an index - the highest-risk rename available for
the least conceptual gain.

**`beliefs/` and `knowledge/`.** These were on the list of dead v1 directories
until a dry run over the real fleet showed 38 and 35 experts with content in
them: belief ledgers, event logs, mutation audits, digests, subscriptions,
about 4MB. They are live v1 storage, not leftovers. The migration reports a
non-empty directory and leaves it alone rather than deleting it, which is the
only reason that was caught before the files were gone.

Renaming storage that something still writes is separate work from renaming the
artifacts of the study loop, and it is not done here.

Only `conversations/` and `documents/` were genuinely empty, and only those are
removed - and only when empty.

## How the migration was safe

**Reads fall back; writes do not.** `expert_layout` resolves the new path
unless only the old one exists. An expert that has not been migrated is fully
readable, one that has been is written correctly, and there is no window where
a reader finds nothing. 57 experts could not be moved atomically, so the
alternative was a flag day.

**One table, not three.** Reader paths, writer paths and the migration's move
list all derive from a single `_PARTS` mapping, so the migration cannot move a
file somewhere a reader will not look.

**Move, do not copy.** A copy leaves two files that both look current and
immediately drift - exactly the confusion `brief.json` and `positions.json`
already caused. Content survives the move and the prior state is in git.

**Dry run by default.** `deepr expert migrate` reports; `--apply` acts. The
plan is produced by the same code that does the work rather than by a second
description of it that can fall out of date.

**Never overwrite.** If both paths exist the source is left alone and the
conflict is reported, because picking a winner silently is how the wrong file
gets kept.

## How it was verified

Health was computed for all 57 experts from a pre-migration backup and from the
migrated fleet, and compared field by field: **0 of 57 differ.** Totals across
the fleet were identical - 70 positions, 499 findings, 147 sources, 5
standpoints. Re-running the migration reports all 57 already current.

## The portrait

`self.json` now carries `appearance`: how the expert says it wants to be
depicted, written by the expert alongside its name and voice.

The prompt this replaces described the *subject* an expert studies, with a
hash-seeded rotation of age, ethnicity and gender for variety. That produces a
picture of the field: two experts on one domain with opposite standpoints
render nearly identically, which is backwards for the thing a portrait is for.
An expert that chooses its own name should choose its own face.

The old prompt remains the fallback for an expert with no self-account yet, and
an unreadable `self.json` degrades to it rather than failing a portrait run.

## Related

- [what-an-expert-is.md](what-an-expert-is.md)
- [expert-v2-identity-and-time.md](expert-v2-identity-and-time.md)
