# Changelog

## 0.4.0 — 2026-09-01

The phosphor moves to the main text, and Emix runs on Windows. The second was
found by testing the first: putting green on a Raspberry Pi console turned up a
bug that had been quietly eating typed-ahead commands on every platform.

### Added

- **Windows support**, covered by CI alongside macOS and Linux on Python 3.11
  through 3.14. Settings and history go where Windows keeps such things —
  `%APPDATA%\emix\` and `%LOCALAPPDATA%\emix\` — because a user told to look
  in `~/.config` is being told about somebody else's computer. The console is
  asked for permission to obey escape sequences, which it does not grant by
  default and without which Emix would print its colours rather than wear
  them.

  Two things are missing there and nowhere else. **Tab completion and command
  history** need `readline`, which Windows does not ship; `emix-shell[windows]`
  pulls in `pyreadline3` to restore them, and the default install still has no
  runtime dependencies. **The RunCPM application bridge** builds on Windows
  but is not yet documented for it. WSL gives you the Linux experience
  unchanged if either matters.

  **The screen colour stays off on Windows**, deliberately. There is no
  termios to hold an OSC 11 conversation over, and the legacy console
  attribute word cannot describe a Windows Terminal profile's arbitrary RGB
  background — a nibble reading as black may be rendering white. Unknown means
  plain, the same rule as a terminal that will not answer; ask for the
  phosphor by name with `--screen bright-green`.
- `--screen COLOUR`, `$EMIX_SCREEN` and a `screen` key in `emix.toml` choose
  the main text colour, including `none`. `$NO_COLOR` and non-terminal output
  still disable colour entirely.
- The bright half of the sixteen ANSI colours — `bright-green`, `bright-white`
  and so on — selectable for either the screen or the hints.
- Issue templates, including one for historical inaccuracies, which are the
  most valuable reports Emix can get.

### Changed

- **Green phosphor now colours the main text, not the hints.** On a terminal
  Emix can tell is dark the whole session is green; a light terminal, or one
  that will not answer, is left plain, because green on a light ground is
  merely hard to read. The colour is set once and inherited rather than
  wrapped around each line, so output meant to read as the machine's own
  carries no escape sequences, and it is re-asserted after a host command or
  an application has had the terminal.
- **Hints are amber against it**, and restore the phosphor behind themselves,
  so a hint interrupts the screen rather than ending it. Both defaults are the
  bright half of the sixteen: many colour schemes render the dim green as a
  muddy yellow-green, too close to amber to tell apart at a glance. A screen
  set to amber gives up the hue and gets white hints instead.

### Fixed

- **The terminal background probe ate commands typed or pasted during the
  first tenth of a second.** `tty.setraw` defaults to `TCSAFLUSH`, which
  discards pending input before the probe can read it. It now uses `TCSANOW`,
  and anything read that was not part of the terminal's reply is replayed as
  the session's first commands. This affected every terminal that does not
  export `COLORFGBG`, not only the Raspberry Pi console where it was found.

  Only *finished* lines are replayed. A half-typed `ERA *.TXT` goes to the
  line editor as a prefix, never to dispatch: nothing is executed on a guess,
  and half a line is a guess. Return is recognised as CR, LF or CRLF, since
  raw and canonical mode spell it differently.
- **The Raspberry Pi's own console now gets the phosphor.** The Linux
  framebuffer console cannot answer OSC 11 and is always black, so the most
  period-looking screen Emix runs on was getting no colour at all.
- **A one-shot `-c` left the terminal green.** Painted output restores the
  phosphor behind itself, but `-c` never ran the lifecycle that puts it out.
  Both routes now share one `Shell.session()`.
- **Host fallthrough could not find a Windows program that was not an `.exe`.**
  `CreateProcess` searches `PATH` but only ever appends `.exe`, so names now
  resolve through `shutil.which`, which honours `PATHEXT`. Unix is untouched,
  where the host already does this itself.

  **Batch files are refused out loud.** Windows runs a `.bat` or `.cmd`
  through its command processor even when Python is told not to use a shell,
  re-parsing the arguments by `cmd.exe` rules that Python does not escape — a
  file named `a&b` would start a second command. Running one would break "no
  shell, ever", so a new `NEEDS_SHELL` code lets the personality word the
  failure in house style while the reason arrives as a marked `Emix:` hint.
- **Windows paths survive command parsing.** `shlex` in POSIX mode reads `\`
  as an escape, so `C:\Users\me\notes.txt` arrived as `C:Usersmenotes.txt`.
- **A configuration file with a Windows path in double quotes now explains
  itself.** TOML reads `\U` as the start of an escape, so
  `drives = ["C:\Users\me"]` failed with "Invalid hex value" — which reads
  like a bug in Emix rather than a quoting rule. The advice appears only when
  a backslash inside quotes is the likely cause.

### Internal

- `readline` is reached through `importlib` and treated as the optional module
  it genuinely is — absent on Windows, present there with `pyreadline3` —
  rather than a POSIX-only one. Platform-specific code is guarded by
  `sys.platform` in `if`/`else` form, so a type checker analyses each branch on
  the platform it belongs to: `mypy --platform win32` passes as well as the
  native run, and both are worth running before a push.

## 0.3.0 — 2026-08-31

Real historical applications, and assistance that teaches rather than
substitutes. **Python 3.11 is now the minimum**, for `tomllib`.

### Added

- Shared `ABOUT` and `CREDIT` commands for every personality (`CREDITS` is an
  alias for the latter).
- `IDEAS.md`, a notebook of optional humour, atmosphere and carefully bounded
  AI integration concepts.
- Document sessions (`emix open FILE --with APP`, `emix apps`): open a host
  file in a real historical application running under an external emulator.
  Emix stages the document under a reversible 8.3 alias, records a
  schema-versioned manifest before launching, detects change by content
  digest, and commits atomically only after review. A RunCPM backend covers
  CP/M; a fake backend keeps the tests free of third-party binaries. A
  session ends when its application exits; `--stay` keeps the guest prompt.
- Application profiles carry a `notes` field, shown before the program
  starts — the home for period conventions a modern user would not guess,
  such as TE's WordStar movement diamond and its forward-deleting Delete key.
- Applications are launchable from inside a personality (`A>TE NOTES.TXT`),
  with `APPS` listing what is installed. Arguments resolve through the drive
  layer, so containment and case folding apply as they do to any other verb.

- An assistance layer that teaches rather than substitutes: `ls` at a VMS
  prompt prints `%DCL-W-IVVERB` verbatim and then names `DIRECTORY`. Mistyped
  verbs and file names get near-miss suggestions. Every added line carries an
  `Emix:` marker, and nothing is ever executed on a guess.
- Emix asks the terminal for its background colour (`COLORFGBG`, then an
  OSC 11 query) and uses green phosphor on a dark screen, amber otherwise. It
  never probes anything that is not an interactive terminal.
- Hints are coloured (amber by default, `--hint-colour`, `$EMIX_HINT_COLOUR`),
  and colour is suppressed for `$NO_COLOR` and any non-terminal output.
- An application verb now accepts a file that does not exist yet, or no file
  at all: `TE NEWFILE.TXT` reserves the name and brings the result home,
  `TE` opens an empty workspace.
- `STRICT` and `--strict/--no-strict`: authentic output only. On by default
  for scripts and pipes, so a script never depends on a guess.
- `EXPLAIN`, which describes the last command or failure using bundled,
  personality-specific knowledge. Offline and deterministic — no model, no
  network, nothing generated.
- Output from commands the original system never had (`ABOUT`, `HELP` under
  CP/M, `APPS`, `EXPLAIN`, `STRICT`) is printed in the hint colour, so
  non-period output never looks like period output. Each personality decides
  which of its verbs are period kit: VMS's `HELP` is real and stays plain,
  CP/M's is an Emix addition and is painted.
- Shared Emix commands (`ABOUT`, `CREDIT`, `APPS`, `STRICT`) print in each
  personality's own casing, so CP/M shouts them like everything else. Web
  addresses are left alone, and hints deliberately keep their normal case:
  they are Emix's voice, not the system's.
- Tab completion offering verbs, applications and file names in each
  personality's own casing.

- An application's own backup and scratch files (`TE.BKP`, `*.BAK`, `*.$$$`)
  are reported as `IGNORED` rather than committed to your documents folder.
  The patterns are per profile.
- A resource ceiling for unattended sessions, and clean interrupt handling: a
  Ctrl-C returns to Emix with nothing written to the host.
- A warning when the terminal is smaller than the application expects.
- A starter set of application profiles — TE, `ED`, MBASIC, DDT, ZEXDOC, LU —
  and a warning in `APPS` when a profile is shadowed by a personality verb.
- Golden-session transcripts covering all three personalities, recorded with
  `pytest --record-golden`. Strict mode is what makes them deterministic.
- `~/.config/emix/emix.toml`: personality, drives, hint colour and strictness
  persist between sessions. The command line always wins.
- CP/M lists a long host name as a reversible alias (`PYPROJ_1 TOM`) and
  accepts it back, without ever renaming the host file.

- `emix --update` reports how this copy was installed, names the newest
  published version, and offers the matching upgrade command — `uv tool
  upgrade`, `pipx upgrade`, `pip install --upgrade`, or `git pull` for a
  checkout. It shows the command and asks before running it. The version
  check is the only network request Emix makes, and only on request.

- The source distribution shipped local working notes, `.coverage` and
  `AGENTS.local.md`. It now excludes them explicitly; hatchling's sdist does
  not honour `.gitignore`.

### Fixed

- A host file edited *during* staging could be silently overwritten on
  commit: the manifest recorded the digest of the source read a second time
  rather than of the copy actually taken, so the conflict check compared the
  host against itself. The digest now describes the staged bytes.
- A guest that crashed, timed out, was interrupted or exited unexpectedly
  could still have its half-written output committed. Backends now report a
  disposition, and only success opens the copy-back path.
- Commit claimed to be all-or-nothing but replaced files one at a time. It
  now takes rollback copies first and restores them if any replacement
  fails. See docs/APPLICATIONS.md for the reasoning and the stronger options.
- Application arguments bypassed the personality's filespec parsing, so
  `TE B:NOTES.TXT` and the aliases `DIR` prints could target the wrong host
  file. Both now go through one resolver, as typed commands do.
- `-c` returned 0 even when the command failed, so scripts could not tell.
- Malformed configuration produced Python tracebacks; `timeout = true` passed
  validation because bools are ints. Shapes, ranges and unknown keys are now
  checked, and duplicate application commands are refused by name.
- `EXPLAIN` could describe one command while diagnosing another, and marked
  only the first line of a multi-line error. Advice is keyed by command as
  well as error code.
- `NO_COLOR` was honoured only after the terminal had already been probed.
- A file the guest deleted was reported as no change at all.
- `SAVE` was documented as one of CP/M's six built-ins but did not exist. It
  now explains that it copied memory Emix has no equivalent of.

### Changed

- Documentation moved into `docs/`; added `AGENTS.md`.
- **Python 3.11 is now the minimum**, for `tomllib` — application profiles
  are TOML and Emix keeps its zero runtime dependencies.

## 0.2.1

Packaging and documentation only; no behaviour change.

- The published description no longer claims the project is unreleased.
- `py.typed` marker added, so the type annotations are visible to consumers.
- The version is single-sourced from `emix/__init__.py`.

## 0.2.0

First public release.

### Added

- Shared personality engine: `host.py` for drives, `shell.py` for the REPL
  and verb table, `errors.py` for codes worded per personality.
- VAX/VMS DCL personality, with verb abbreviation, `/QUALIFIERS`, and the
  explicit-version `DELETE` rule.
- IBM VM/CMS personality, with three-token `FILENAME FILETYPE FILEMODE`
  fileids and `Ready;` responses carrying return codes.
- Multiple drives via repeatable `--mount`, named in each personality's own
  style, and `-c` to run a command and exit.
- Persistent readline history per personality.

### Fixed

- Symlinks pointing out of a drive were readable and listed. Paths are now
  checked against the drive root after symlink resolution.
- Case-ambiguous lookups picked whichever host file `iterdir()` yielded
  first. They now fail loudly.
- Listings printed identical rows for names differing only by case, naming
  neither file usefully. Found on a Raspberry Pi; invisible on macOS.
- The banner reprinted on every interrupt.
- `.upper()` and `.casefold()` were used inconsistently, so a file could be
  listed and then refused when opened.

### Changed

- CP/M now exposes its real six CCP built-ins, with `PIP` and `STAT` shown
  as the transient programs they were rather than as built-ins.
- `cmd.Cmd` replaced; it cannot express DCL abbreviation or qualifier syntax.
- Names too long for 8.3 are shown in full rather than truncated, because a
  listing that names a file you cannot type back is worse than a misaligned
  column.
