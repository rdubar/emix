# Historical applications in Emix

**Status:** Phase 0 prototyped and working; the rest is a proposal.
**Supersedes:** the native-8080 plan in [ROADMAP.md](ROADMAP.md) §0.5 — see
[What this replaces](#what-this-replaces), which is a change of *order*, not
of destination.

## Summary

Emix should let someone open a real host file in a real historical
application without first becoming the operator of a simulated computer:

```sh
emix open ~/Documents/notes.txt --with te-cpm
```

Emix configures the drives, adapts the filename, launches the emulator,
attaches the terminal, detects what changed, and offers the result back to
the host. Specialist projects keep owning CPU and machine emulation. Emix
owns the document lifecycle, the safety policy, and the consistency.

> Real historical applications, modern files, explicit boundaries.

This works today for CP/M. `emix open` stages a document, launches TE under
RunCPM, and reviews the result.

## What this replaces

`ROADMAP.md` §0.5 argued for writing an 8080 interpreter and a BDOS in
Python, on two good grounds: the emulator *is* the sandbox, and the BDOS *is*
`host.DriveSet`, which already exists. Both still hold. The change here is
that an external backend gets a real application running now, and the cost of
that shortcut is visible and bounded.

The cost is precise. When Emix owns the BDOS, a guest writes straight through
`DriveSet` and there is nothing to reconcile. When an external emulator owns
it, Emix must reconstruct after the fact what happened:

| | Native BDOS (§0.5) | External backend (built) |
| --- | --- | --- |
| Containment | free, already written | rebuilt outside Emix |
| File model | live host files | stage, review, commit |
| Filename mapping | inside the FCB path | a manifest subsystem |
| Change detection | not a concept | digests and review |
| Runs real CP/M software | after ~250 opcodes + BDOS | working now |

So `src/emix/apps/` is not a richer design than §0.5. It is the bill for
deferring §0.5, and it is worth paying only because it answers the product
question — *does this feel delightful?* — before the expensive work starts.

Two corrections to §0.5 while it stands:

- **The performance worry targets the wrong workload.** CPython's 300k–1M
  instructions/second is marginal for games. A text editor is blocked on
  `BDOS 1` waiting for a keystroke essentially always. Editors are the best
  case for a slow interpreter, and editors are what this feature is for.
- **Do not rewrite a BDOS from the specification alone.** RunCPM's real asset
  is a decade of fixes for how actual CP/M programs misbehave. Read its BDOS
  as documentation of reality.

## Two backend classes, not one pool

The most useful thing the prototype settled:

- **Native** (CP/M, eventually): Emix owns the BDOS over `DriveSet`. Live
  host files, no staging, no commit prompt. The staging machinery above is
  simply not used.
- **External** (DOS, VMS, permanently): nobody is writing an x86 in Python.
  DOSBox-X stays a subprocess forever, so staging, manifests and
  review-before-commit are permanent there.

The adapter protocol therefore earns its place twice: it lets a disposable
CP/M spike and a permanent DOS adapter wear one interface, and it is the seam
that lets the spike be replaced without touching the personalities.

## Non-goals

- Reimplement every CPU the chosen backends support.
- Bundle proprietary operating systems, ROMs or applications.
- Promise every historical binary will run.
- Silently convert proprietary document formats.
- Give a guest arbitrary host paths, network access or a shell.
- Hide the difference between authentic guest behaviour and Emix convenience.
- **Vendor** an emulator into Emix's source tree. (Adapting a backend's *CPU
  core* later is a different act, explicitly allowed by RunCPM's MIT licence.)

## Tension with the project's first principle

`ROADMAP.md` principle 1 says the host stays real: files belong to Unix, and
a personality is "not a container around them". A copy-on-write staging
directory is exactly a container around them, and `README.md` opens by saying
Emix does not run historical binaries.

This is the one bounded exception, framed the way §0.5 framed itself. It
should stay conspicuous rather than be smoothed over: the staging model is a
consequence of not owning the BDOS, and for CP/M it is temporary.

## What is built

`src/emix/apps/`, 107 tests passing, no new runtime dependencies.

```
emix open FILE --with APP     stage, run, review, commit
emix apps                     list profiles and check backends
```

- `names.py` — reversible 8.3 aliases. Truncation announces itself
  (`PYPROJ_1.TOM`); character folding does not (`A_B.TXT`), because
  `PYPROJEC.TOM` looks like a real name and is not one. This is also
  roadmap 0.3's alias item, built once for both users.
- `manifest.py` — schema-versioned JSON, written and fsynced **before** the
  guest launches, so a crash is recoverable rather than mysterious. Content
  digests, never mtimes.
- `session.py` — stage one document, detect change, refuse to commit over a
  host file that moved underneath, replace atomically, all-or-nothing.
- `backends.py` — the adapter protocol, a RunCPM adapter, and a fake so the
  test suite never needs a third-party binary installed.
- `profiles.py` — TOML profiles. Emix ships no software; a profile only
  describes what the user already has.

### What Phase 0 actually found

- RunCPM is not "ancient": created 2016, last pushed six days before this was
  written, MIT, one open issue. Its plain-C style reflects also targeting an
  Arduino, not neglect.
- It resolves drives against **cwd**, so one installed binary serves every
  session and Emix never copies or patches the emulator.
- Auto-launch needs no pty: a CP/M `$$$.SUB` batch file drives the CCP, and
  the emulator inherits the real terminal.
- Build with `CCP=INTERNAL`; every other CCP needs an external binary at
  runtime.
- `TE.COM` on RunCPM's sample disk is a freely distributable full-screen
  editor. This answers the "we need one redistributable editor" risk without
  touching WordStar's licensing.
- **A document session must end with the application.** First contact with a
  real user found this immediately: TE exits, and CP/M 2.2 returns you to its
  own command processor, which has six built-ins, no `HELP`, and no `ls` or
  `cat`. Authentic, and a bad place to be dropped by a command that only said
  "open this file". The session now chains `EXIT.COM` after the application,
  and `--stay` is the opt-in for anyone who wants the prompt (with a printed
  orientation, since CP/M provides none).
- **The quirks are period-authentic, not bugs to paper over.** TE's key map
  lives in a `TE_CONF` block in the binary (offset `0x127b` in v1.73): a
  23-byte table whose movement keys are the WordStar diamond — `^E` `^S` `^D`
  `^X`, `^R`/`^C` for paging — and whose `Delete` action is bound to `^G`,
  exactly as WordStar had it. Its `DelRight` is `0x7F` and `DelLeft` is
  `0x08`, so a modern Delete key deletes forwards. CP/M itself had no
  full-screen editing to have an opinion; its line editor backspaced with
  `^H` and *echoed* the character on `RUBOUT`, a teletype convention. So the
  right response is to teach the convention, not hide it: profiles carry a
  `notes` field, shown before the application starts.
- **TE rejects `~` and `-` in a command tail, though the CCP parses both.**
  The first real compatibility quirk, and it belongs to the *application*,
  not the backend — so the collision suffix is a profile setting defaulting
  to `_`. Expect profiles, not adapters, to accumulate this knowledge.

## Configuration

```toml
# ~/.config/emix/apps.toml
[app.te-cpm]
backend = "runcpm"
program = "TE.COM"
application = "~/dev/RunCPM/DISK/A/0"
terminal = "vt100"
# alias-suffix = "_"    # TE rejects "~" and "-"
# executable = "~/dev/RunCPM/RunCPM/RunCPM"
```

TOML via `tomllib`, which sets the Python floor at 3.11 — cheaper than an INI
schema with invented nesting, and cheaper than a `tomli` dependency on a
project whose pitch is having none. Persistent drive mappings should wait for
roadmap 0.3's configuration file so there is one precedence model.

## Safety model

1. Backends receive only configured drives.
2. No generated command passes through a host shell.
3. A document session exposes one file, not its folder.
4. Changes are reviewed before commit.
5. Host updates are atomic; the original survives a failure.
6. Commit refuses when the host file changed during the session.
7. The manifest lives outside every mounted drive.
8. Network and clipboard capabilities are off, and unimplemented.
9. **Not yet built:** a resource ceiling. This is not theoretical — TE spins
   and floods output when stdin is not a terminal.

The emulator process is host software and is trusted as such. Emix's boundary
protects the host from the *guest program*, not from a malicious emulator.

## Next

**Phase 1 — finish the CP/M session.** A resource ceiling and interrupt
handling. Terminal geometry in the profile (TE assumes 80×24). A rule for
guest files whose names cannot map home. Golden-transcript tests.

**Phase 2 — DOS under DOSBox-X.** One question first, before any adapter:
DOSBox-X is SDL-based and will open its own window, which breaks "exit
returns you to where you were" harder than CP/M does. Verify in-terminal
attachment is possible *before* committing to DOS as target two.

**Phase 3 — native CP/M.** Port a Z80 core, write the BDOS over `DriveSet`,
validate against `ZEXDOC`/`ZEXALL` — both already on RunCPM's disk. Live host
files; the staging path stops being used for CP/M.

**Later.** Folder sessions for trusted profiles. Word-processor formats, with
an exact-byte fallback. Invocation from inside the CP/M personality, once the
host-level workflow is stable.

**Deliberately not planned.** VMS through SIMH. Staging into a VMS guest means
driving a login over a pty and dealing with RMS record structure; none of it
answers the question this feature exists to answer.

## Open questions

1. Should a trusted profile be able to auto-commit after a normal exit, or
   must every session confirm?
2. Is `--stay` the right shape for reaching the guest prompt, or should that
   be a separate `emix app APP` rather than a flag on `open`?
3. Should a document session ever expose companion files (`*.BAK`, includes),
   and if so by whose declaration?
4. What is this called in user-facing text? "Bridge" is good internal
   vocabulary; the command is what people will actually learn.
5. Does `emix app APP` (no document) earn its place, or is `open` enough?

## The question that still matters

Does using a historical editor on a modern file feel delightful once the
emulator administration disappears? The machinery now exists to find out.
Everything past Phase 1 should wait on the answer.
