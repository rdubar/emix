# Changelog

## Unreleased

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

### Changed

- CP/M now exposes its real six CCP built-ins, with `PIP` and `STAT` shown
  as the transient programs they were rather than as built-ins.
- `cmd.Cmd` replaced; it cannot express DCL abbreviation or qualifier syntax.
- Names too long for 8.3 are shown in full rather than truncated, because a
  listing that names a file you cannot type back is worse than a misaligned
  column.
