# Working on Emix

Emix presents the commands, syntax and errors of historical systems over
ordinary host files. It is not a CPU emulator — with one deliberate,
bounded exception described in [docs/APPLICATIONS.md](docs/APPLICATIONS.md).

## Commands

```sh
uv sync                                    # environment
uv run pytest -q                           # 222 tests
uv run ruff check . && uv run ruff format --check .
uv run mypy                                # strict, src/emix only
uv run emix cpm                            # try it
```

`uv run emix` runs the *installed* console script. After changing `cli.py`'s
entry points run `uv sync --reinstall-package emix-shell`, or the old parser
will answer.

## Layout

```
src/emix/
  errors.py         symbolic error codes, worded per personality
  host.py           drives: containment, case folding, ambiguity
  shell.py          REPL, verb table, abbreviation, host fallthrough
  assist.py         hints, translations, explanations, completion
  config.py         persistent settings; command line always wins
  terminal.py       background detection, so green phosphor is only used on dark
  cli.py            argument parsing; `open` and `apps` subcommands
  personalities/    cpm.py, vms.py, cms.py — vocabulary and house style
  apps/             document sessions over external emulators
    names.py        reversible 8.3 aliases
    manifest.py     the durable session record; schema-versioned
    session.py      stage, detect change, review, atomic commit
    backends.py     the adapter protocol; RunCPM and a fake
    profiles.py     TOML application profiles
    runner.py       one session, end to end
tests/golden/       whole-session transcripts; rerecord with
                    `uv run pytest --record-golden`
docs/               ROADMAP.md, APPLICATIONS.md, IDEAS.md
```

## Invariants — do not regress these

1. **Zero runtime dependencies.** Python 3.11+ standard library only. Dev
   tooling is fine. TOML uses `tomllib`, which is why the floor is 3.11.
2. **Drives are sealed after symlink resolution.** Every host path goes
   through `DriveSet`, which resolves and *then* checks containment.
3. **No shell, ever.** `run_host_command` takes an argument list.
4. **The manifest is written before a guest launches.** It is the only
   recovery record if Emix dies mid-session.
5. **Content digests, never mtimes**, decide what a guest changed.
6. **Commit is all-or-nothing**, and refuses to overwrite a host file it
   *observes* has changed underneath the session — checked at preflight and
   again immediately before each write. This is best-effort detection, not
   exclusion: a write landing inside the final handoff is still lost. Never
   restate it as a guarantee; `docs/APPLICATIONS.md` holds the exact contract.
   A failed commit never claims an undo it did not perform, and its workspace
   is always kept.
7. **Tests never require a third-party binary.** Use `FakeBackend`.
8. **Assistance never alters authentic output.** The period response prints
   first and verbatim; hints go below it under the `Emix:` marker. A test
   asserts assisted output starts with exactly the strict output.
9. **Nothing is executed on a guess.** Hints name a command; the user types
   it. Strict mode is the default for scripts and pipes.

## House style

Comments explain *why*, not what. The existing modules set the register:
module docstrings state the problem the module solves, and a comment earns
its place by recording a decision or a trap. Match it — reviewers read this
project for its prose as much as its behaviour.

Test names are sentences: `test_commit_refuses_when_the_host_file_moved_underneath_the_session`.

## Running the CP/M application bridge

Emix ships no emulator and no CP/M software. To exercise `emix open` locally:

```sh
git clone https://github.com/MockbaTheBorg/RunCPM ~/dev/RunCPM
cd ~/dev/RunCPM/RunCPM && make -f Makefile.macosx CCP=INTERNAL
unzip -o ~/dev/RunCPM/DISK/A0.zip -d ~/dev/RunCPM/DISK/
```

`CCP=INTERNAL` matters: the other CCPs need an external `CCP-*.60K` file at
runtime. Then write `~/.config/emix/apps.toml` (see `emix apps` for a
template) and run `emix open FILE --with te-cpm`.

### Backend facts worth not rediscovering

- RunCPM resolves drives against **cwd** (`FILEBASE "./"`), so one binary
  serves every session via `subprocess(cwd=session_root)`.
- Auto-launch uses a CP/M `$$$.SUB` batch file: 128-byte records, each a
  length byte plus text, **consumed from the end**, so records are written in
  reverse order.
- `EXIT.COM` on the sample disk terminates RunCPM cleanly, and is chained as
  the last `$$$.SUB` record so a document session ends with its application
  instead of stranding the user at the CCP. `--stay` suppresses it.
- `TE.COM` (Miguel Garcia, v1.73) is a freely distributable full-screen
  editor on that disk — the demo target, and the only editor safe to
  reference in docs. Its menu is ESC then a letter: `S`ave, save `A`s,
  e`X`it, `H`elp.
- **TE does not preserve bytes.** It converts tabs to spaces and illegal
  characters to `?` when reading, and writes its own `TE.BKP` backup. So a
  round trip through TE is lossy for tab-indented files, which sits badly
  with the "preserve bytes by default" goal and needs a profile-level
  warning before Phase 1 calls this finished.
- **TE rejects `~` and `-` in a command tail** although the CCP parses both
  correctly. That is an *application* quirk, not a backend one, which is why
  the collision suffix is a profile setting defaulting to `_`.
- With stdin at EOF (not a terminal) TE spins and floods output. Harmless
  interactively; relevant to the unimplemented resource ceiling.
- **The CCP rejects an explicit `.COM`.** `A:TE.COM` happens to run but
  `A:MBASIC.COM` answers `A:MBASIC.COM?`. The adapter strips the extension,
  which is also what a period user would have typed.
- **TE's key map is in the binary, not in CP/M.** The `TE_CONF` block (offset
  0x127b in v1.73) holds a 23-byte key table. Movement is the WordStar
  diamond — `^E ^S ^D ^X` for up/left/right/down, `^R`/`^C` for page. Deletion
  is `DelRight = 0x7F` and `DelLeft = 0x08`, so a Mac's Delete key (which
  sends 0x7F) deletes forwards. Use Control-H for a backspace-delete, or set
  the terminal to send `^H`. This is an application quirk, and the profile is
  where such knowledge belongs.
