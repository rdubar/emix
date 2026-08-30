# Changelog

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
