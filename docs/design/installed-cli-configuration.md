# Installed CLI configuration

Status: implementation decision, October 11, 2026. Addresses issue #200.

## Problem

`deepr init` writes the current folder's `.env`, while an installed package
discovers `.env` relative to its Python module. The initialized data paths and
ceilings therefore disappear on the next invocation. Consolidated settings
also omit dotenv provenance, so `config show` can report defaults despite
effective environment overrides.

## Decision

Use the existing configuration seam in `deepr.config` for dotenv discovery.
Initialization and `config set` write the same file the runtime selects:
`~/.deepr/.env` by default, or the operator's explicit `DEEPR_ENV_FILE` path.
`init --local-env` creates the current folder's `.env` and explains how to
select it explicitly. Ordinary invocations do not search parent folders or
package installation directories for ambient configuration.

Process variables retain precedence. An explicitly selected project file
precedes the per-user file; missing values may fall back to the user file.
`PYTHON_DOTENV_DISABLED` continues to disable file loading for tests and
operators. The shared loader records file paths and variable provenance, never
credential values, and does not reload keys after CLI startup quarantine.
Both AppConfig and consolidated Settings observe this one loader. Doctor and
configuration inspection name the files actually read, without implying that
configured monetary ceilings authorize paid dispatch.
HTTP app imports use the same one-shot loader. Credential inventory and writes
use the same explicit/user selection and dotenv parser without injecting keys
into the environment; their existing bounded reads and live-check gates remain.
Resolve the selected and fallback paths to absolute paths before evaluating any
dotenv file, and retain that selection for the process lifetime, including when
file loading is disabled. A selector stored inside a dotenv file cannot redirect
later reads or writes. Changing the working folder or process selector does not
change an existing selection; restart to select a different configuration.
OpenRouter account-control credential lookup uses those same bound files and
the shared non-interpolating reader under its existing 64 KiB bound. Process
then quarantined credentials retain precedence over selected then fallback
files. Normal startup dotenv expansion remains unchanged; file inventory does
not inject credentials or import the CLI from the provider layer.

Keep existing expert, report, runtime and queue defaults when no relocation
was selected. An explicit `--data-dir` stores a stable absolute directory so
changing the working folder does not relocate initialized data. Preserve
existing file comments and settings, parse supported dotenv quoting, and keep
new secret-bearing configuration files private where the platform supports
POSIX permissions. Do not copy an unrelated folder's `.env.example` into
per-user configuration.

## Preserved boundaries and alternatives

Configuration loading is deterministic storage and side-effect control under
[AGENTIC_BALANCE](../plans/AGENTIC_BALANCE.md); model judgment is unaffected.
Keep startup key quarantine, the canonical cost ledger, monotonic checkout
ceilings and paid authorization unchanged. A configured ceiling and effective
paid authority remain distinct. Automatically searching the current folder
would change provider endpoints and credentials when navigating directories;
explicit project selection makes that scope inspectable. A second settings
loader or new dependency would duplicate the existing seam.

## Verification

Reproduce ignored initialization in an isolated home and unrelated working
folder. Exercise the installed entry point in fresh processes, global and
explicit project files, environment precedence, disabled loading, quoted
values, missing selected files, preserved comments, and changes of directory.
Verify doctor and both configuration views agree on initialized paths, source
reporting contains no credentials, and later settings access cannot restore
quarantined keys. Retain the existing spend-cap refusal and provenance tests.
Run focused CLI/settings tests, the repository's fast gates and full unit
coverage, then exact-head and resulting-main CI. All validation is offline.

The existing locked python-dotenv 1.2.2 parser and writer handle dotenv syntax;
Deepr serializes quotes/backslashes before writing so paths round-trip without
changing dependencies. See the [upstream file format and environment precedence](https://bbc2.github.io/python-dotenv/).
