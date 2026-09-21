# Python Engineering: brief

## In sixty seconds

For new Python engineering projects, use pytest's importlib mode and src layout to isolate test execution from local code. Avoid threading for CPU-bound tasks due to the GIL; use multiprocessing with spawn or forkserver on POSIX. Handle asyncio cancellation by propagating CancelledError and using try/finally blocks. For tarfile extraction, always specify an explicit filter (data or fully_trusted) as defaults vary by version and lack safety guarantees. In free-threaded Python, do not rely on built-in type locking; use explicit synchronization primitives. Static typing is an opt-in overlay with no strict gradual guarantee.

## Where I land, and why

1. **What is the recommended pytest import mode for new projects?**
   - Stance: Use --import-mode=importlib instead of the default prepend mode.
   - Because: The prepend mode modifies sys.path, inadvertently exposing the local application package and causing side effects where tests import local code instead of the installed version. The importlib mode avoids these side-effects by not modifying sys.path, resulting in more predictable behavior.
   - Likelihood it holds: almost certain (95-99%)
   - Confidence in that basis: high (Direct mechanism description of side-effects and explicit failure correction.)
   - Would change my mind: A finding demonstrating that importlib mode introduces a critical performance regression or incompatibility with a specific testing framework that cannot be worked around.
   - Check on 2026-10-20: Verify if using --import-mode=importlib causes test failures in a standard project setup where prepend mode passes, specifically regarding import isolation.
   - Rests on: The 'importlib' mode is recommended because it avoids the side-effects of modifying... (mechanism-c9096d6b6f3e1126); failure finding (failure-67bec0919340a1e1)
   - Evidential depth: 1 source(s), 1 publisher(s)

2. **Does Python 3.13 enable true parallelism with threads?**
   - Stance: No, standard Python 3.13 does not enable true parallelism with threads; the GIL remains active by default.
   - Because: The GIL is the primary constraint on CPU-bound parallelism in standard builds, restricting execution to a single thread at a time. Free-threaded builds exist but are not the default; they require specific compile-time variables and runtime configuration to disable the GIL.
   - Likelihood it holds: almost certain (95-99%)
   - Confidence in that basis: high (Explicit description of GIL as a constraint and lack of default free-threading.)
   - Would change my mind: Evidence that a standard Python 3.13 installation (without special build flags) executes CPU-bound threaded code in parallel on multi-core systems.
   - Check on 2026-10-20: Run a CPU-bound threaded benchmark on a standard Python 3.13 install and verify if CPU utilization exceeds 100% across cores.
   - Rests on: The GIL is the primary constraint on CPU-bound parallelism in standard builds (mechanism-f07d62bd42ac6aa4); failure finding (failure-3d5731b958f86b53)
   - Evidential depth: 1 source(s), 1 publisher(s)

3. **What is the default multiprocessing start method on POSIX systems?**
   - Stance: The default start method on POSIX systems is 'forkserver', not 'fork'.
   - Because: Performance and safety trade-offs drive the selection. The forkserver method is chosen over fork to retain performance while avoiding the incompatibilities of forking multithreaded processes, which can cause crashes.
   - Likelihood it holds: likely (55-80%)
   - Confidence in that basis: moderate (Explicit statement on trade-offs and default selection logic.)
   - Would change my mind: Documentation or empirical evidence showing that 'fork' is the default on a specific POSIX variant (e.g., macOS) in Python 3.13.
   - Check on 2026-10-20: Check sys.multiprocessing.get_start_method() on a standard Python 3.13 installation on a POSIX system.
   - Rests on: Performance and safety trade-offs drive the default start method selection across... (mechanism-ff16e4529d7dc660); failure finding (failure-2dc3948990b98e61)
   - Evidential depth: 1 source(s), 1 publisher(s)

4. **How does Python handle task cancellation in asyncio?**
   - Stance: Cancellation is a mechanism to wake up suspended execution points by injecting an exception at the next await point, not immediate termination. It requires explicit cleanup via try/finally blocks.
   - Because: The cancellation signal does not stop code instantly; it injects an exception at the next await point. Suppressing asyncio.CancelledError without clearing the state causes misbehavior in structured concurrency components like TaskGroups. Cancellation counts are preserved across nested boundaries.
   - Likelihood it holds: almost certain (95-99%)
   - Confidence in that basis: high (Detailed mechanism of signal injection and state management.)
   - Would change my mind: Evidence that asyncio.CancelledError can be safely suppressed without clearing state or using try/finally in a TaskGroup context without causing misbehavior.
   - Check on 2026-10-20: Write a coroutine that catches CancelledError, suppresses it, and verify if the parent TaskGroup or timeout() behaves incorrectly.
   - Rests on: Cancellation is a mechanism for waking up suspended execution points rather than... (mechanism-1e6a17d1a4dbde3c); Cancellation is a stateful flag that must be explicitly cleared to suppress errors (mechanism-5938774212903521); failure finding (failure-1d785b9c688f5c2d)
   - Evidential depth: 1 source(s), 1 publisher(s)

5. **What are the security implications of using tarfile extraction?**
   - Stance: Using tarfile without an explicit filter is insecure; default behavior varies by version (pre-3.14 defaults to fully_trusted), allowing path traversal and symlink attacks.
   - Because: The tarfile module's extraction filter logic contains flaws where rejection signals can be ignored during fallback operations. Vulnerabilities allow file modification outside the destination directory via hard links and symlinks. Pre-defined filters do not prevent denial-of-service or live data tampering.
   - Likelihood it holds: almost certain (95-99%)
   - Confidence in that basis: high (Explicit vulnerability descriptions and failure modes.)
   - Would change my mind: Evidence that a specific tarfile version (e.g., 3.14+) enforces a safe default filter ('data') without user configuration.
   - Check on 2026-10-20: Extract a crafted tar archive with a symlink attack vector using the default settings in Python 3.13 and verify if it modifies files outside the destination.
   - Rests on: The 'tarfile' module's extraction filter logic contains a flaw where it ignores rejection... (mechanism-cba19a0154b8d2ae); failure finding (failure-67bec0919340a1e1); failure finding (failure-e5f0fcb3410d2a94)
   - Evidential depth: 3 source(s), 2 publisher(s)

6. **How should one handle threading in free-threaded Python?**
   - Stance: Do not rely on internal locking of built-in types; use explicit synchronization primitives like threading.Lock.
   - Because: Internal locking of built-in types is an implementation detail, not a guaranteed contract. Thread safety in free-threaded builds is an aim, not a default guarantee. Relying on these locks can lead to undefined behavior under heavy concurrency.
   - Likelihood it holds: almost certain (95-99%)
   - Confidence in that basis: high (Explicit distinction between implementation detail and guarantee.)
   - Would change my mind: Documentation stating that internal locking of built-in types is now a guaranteed contract for all future free-threaded builds.
   - Check on 2026-10-20: Run concurrent modifications on a dict in a free-threaded build and verify if race conditions occur without explicit locks.
   - Rests on: Internal locking of built-in types is an implementation detail, not a guaranteed contract (mechanism-188bc9cdfdc6a758); failure finding (failure-aee6b8bebee66bc9)
   - Evidential depth: 1 source(s), 1 publisher(s)

7. **What is the recommended approach for handling untrusted input in Python?**
   - Stance: Avoid using pickle, shelve, or random module for untrusted data; use secure alternatives like secrets module and validate inputs strictly.
   - Because: Multiprocessing communication channels (pickle) and shelve are unsafe for untrusted sources due to deserialization risks. The random module is not suitable for security purposes. Untrusted input requires validation, sanitization, and size limits.
   - Likelihood it holds: almost certain (95-99%)
   - Confidence in that basis: high (Explicit security warnings and failure modes.)
   - Would change my mind: Evidence that a specific version of pickle or shelve has been cryptographically secured against deserialization attacks for untrusted data.
   - Check on 2026-10-20: Attempt to execute arbitrary code via a malicious payload sent through multiprocessing Connection.recv() or shelve in Python 3.13.
   - Rests on: failure finding (failure-e5f0fcb3410d2a94); failure finding (failure-65c558e2072aaccf); failure finding (failure-e0c9d3f41c6233fd)
   - Evidential depth: 1 source(s), 1 publisher(s)

## Settled, live, unknown

**Settled (skip these)**
- pytest importlib mode is preferred over prepend to avoid sys.path side-effects
- GIL prevents CPU-bound parallelism in standard Python builds
- asyncio cancellation requires propagation and explicit cleanup, not suppression
- tarfile extraction requires explicit filters due to inherent vulnerabilities
- Built-in type locking is not a guarantee in free-threaded builds

**Live**
- Default multiprocessing start method on all POSIX systems (forkserver vs fork nuances)
- Exact default tarfile filter behavior across all Python versions prior to 3.14
- Performance impact of free-threaded builds on single-threaded code

**Genuinely unknown**
- Long-term stability guarantees for internal locking in future free-threaded releases
- Complete mitigation of denial-of-service attacks via tarfile filters alone

## The numbers that matter

- Python 3.14 default filter change
- CVE-2026-82049 (tarfile vulnerability)
- sys._is_gil_enabled() check

## What people try that does not work

- Using pytest's default 'prepend' mode, which exposes local code and causes import confusion.
- Relying on the GIL to provide thread safety for CPU-bound tasks, leading to no performance gains.
- Catching asyncio.CancelledError without propagating it, breaking structured concurrency.
- Extracting tar files without specifying a filter, relying on version-dependent defaults that may be insecure.
- Relying on internal locking of built-in types in free-threaded builds, causing race conditions.
- Using pickle or shelve for untrusted data, leading to code execution vulnerabilities.

## Questions I expect

**Can I rely on the 'gradual guarantee' to ensure that removing type annotations won't introduce new static errors?** (this one costs me something)
No. The gradual guarantee is a heuristic guideline, not a strict enforcement mechanism. Removing annotations may result in additional static type errors depending on the checker's implementation.
_Asked because: Developers often assume type safety is preserved when removing annotations, leading to false confidence in refactoring._

**Is it safe to use the 'data' filter for all tarfile extractions without further inspection?** (this one costs me something)
No. Even with filter='data', tarfile is not suited for extracting untrusted files without prior inspection. It does not prevent denial-of-service attacks or handle live data tampering.
_Asked because: Users may assume the 'data' filter provides complete security, leading to reliance on it as a silver bullet._

**Does the 'src' layout solve all import resolution issues for editable installations?** (this one costs me something)
No. While it enforces separation, editable installations using path configuration files can still expose non-importable project files to the import system, creating discrepancies between editable and regular installation behaviors.
_Asked because: Developers may assume src layout is a complete fix for all packaging and import issues._

## Who this rests on

| Origin | Sources | Trust | Note |
|---|---|---|---|
| pytest.org | 1 | secondary | - |
| python.org | 18 | secondary | 18 sources from one publisher; repetition here is not independent corroboration. |

## Read this brief knowing

- 1 origin(s) supply several sources each. Repetition within one publisher is not independent corroboration.
- No position records unresolved dissent. That is possible, and it is also what a brief looks like when disagreement has been averaged away; check the study findings for contention the brief did not carry forward.

## Limitations

- 11 of 101 findings were not verifiable against the retained corpus. Positions resting on them inherit that.
- 19 source(s) collapse to 1.2 independent origin(s). Agreement between them is one publisher agreeing with itself, and any finding that reads as corroborated here is not.
- python.org supplies 95% of this corpus, so it sets what can be concluded. A contention lens will mostly find that publisher disagreeing with itself.
- Corpus was read in 8 chunk(s) of up to 14000 chars. Each lens saw one chunk at a time, so cross-chunk connections may be missed.
- 20 quoted anchor(s) were not found in the retained corpus. Those findings are labeled ungrounded, not removed; review before use.
- 4 studied source(s) produced no anchored finding.

---

Derived from study findings over a retained corpus. Positions are the expert's reading of that evidence, not verified fact; each states what would overturn it.
