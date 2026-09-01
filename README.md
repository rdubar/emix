# Emix

[![PyPI](https://img.shields.io/pypi/v/emix-shell)](https://pypi.org/project/emix-shell/)
[![CI](https://github.com/rdubar/emix/actions/workflows/ci.yml/badge.svg)](https://github.com/rdubar/emix/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/emix-shell)](https://pypi.org/project/emix-shell/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Emix lets a modern computer present itself as an older one — and, when you ask
it to, run that older computer's real software on your real files.

Those are two different things, and Emix keeps them clearly apart:

- **A personality is not an emulator.** `emix cpm` reproduces CP/M's commands,
  syntax, output formats and error messages in Python, over ordinary host
  files. No 8080 is involved.
- **An application is.** `A>ED LETTER.TXT` loads a real `ED.COM` and executes
  real Z80 instructions through [RunCPM](https://github.com/MockbaTheBorg/RunCPM),
  on a document staged from your own folder. Emix owns the drives, the
  filenames and what comes back out; it does not own the CPU.

Emix ships no operating systems and no applications — you supply software you
already have, and Emix supplies the knowledge of how to drive it.

The full guide is [docs/MANUAL.md](docs/MANUAL.md).

Three personalities ship today:

| Personality | System | Prompt | Vocabulary |
| --- | --- | --- | --- |
| `cpm` | Digital Research CP/M 2.2 | `A>` | `DIR`, `ERA`, `REN`, `TYPE`, `USER`, plus `PIP` and `STAT` |
| `vms` | DEC VAX/VMS DCL | `$ ` | `DIRECTORY`, `TYPE`, `COPY`, `RENAME`, `DELETE`, `SET`, `SHOW` |
| `cms` | IBM VM/CMS | *(none)* | `LISTFILE`, `TYPE`, `COPYFILE`, `RENAME`, `ERASE`, `QUERY` |

They are not three programs. They are three vocabularies over one engine, and
the differences between them — CP/M's `NEW=OLD` argument order, DCL's
abbreviations and `/QUALIFIERS`, CMS's three-token `FILENAME FILETYPE
FILEMODE` — are what the engine exists to express.

`TRANSLATE` is where that becomes visible, because it answers in all three at
once:

```text
A>TRANSLATE COPY
TO COPY A FILE:
  CP/M 2.2  PIP NEW=OLD
  OPENVMS   COPY
  VM/CMS    COPYFILE

A>TRANSLATE CD
TO CHANGE DIRECTORY:
  CP/M 2.2  -- NO EQUIVALENT
            CP/M 2.2 HAD NO DIRECTORIES AT ALL, ONLY DRIVES A: TO P:
  OPENVMS   SET DEFAULT
  VM/CMS    -- NO EQUIVALENT
            CMS REACHED OTHER DISKS BY FILEMODE LETTER RATHER THAN BY MOVING
```

A gap is reported rather than skipped. What a system *cannot* say is usually
the more interesting fact about it, and it is the one a table of equivalents
would quietly hide.

`BECOME` goes further and hands the session over, keeping your files exactly
where they are:

```text
A>DIR
A: NOTES    TXT

A>BECOME VMS
$ DIRECTORY
Directory DKA0:[000000]

NOTES.TXT;1

$ BECOME CMS
Ready;
LISTFILE
NOTES    TXT      A1
```

One file, one directory, three vocabularies, one session. The drives come
across renamed — the same host folder answers to `A:`, `DKA0:` and filemode
`A` — and the drive you were on is the drive you land on.

## Install

```sh
uv tool install emix-shell     # or: pipx install emix-shell
emix cpm
```

To try it without installing anything:

```sh
uvx --from emix-shell emix cpm
```

The distribution is **`emix-shell`** but the command is **`emix`**, which is
why `uvx` needs `--from`. PyPI rejects the bare name `emix` as too similar to
the existing `emux`, `emx` and `emi` projects.

To update later, ask Emix — it knows how it was installed and offers the
matching command rather than guessing:

```sh
emix --update
```

Emix has no runtime dependencies beyond Python 3.11 or newer. If `uv` warns
that `~/.local/bin` is not on your `PATH`, run `uv tool update-shell` and open
a new terminal.

**macOS, Linux and Windows**, all three covered by CI on Python 3.11 to 3.14,
and the Raspberry Pi's own console as well as SSH into it.

Two things are Unix-only. Tab completion and command history need `readline`,
which Windows does not ship — `uv tool install "emix-shell[windows]"` adds
`pyreadline3` and restores both. The RunCPM application bridge builds on
Windows but is not yet documented for it. WSL gives you the Linux experience
unchanged if either matters.

### From source

Running from a checkout needs no install step at all:

```sh
git clone https://github.com/rdubar/emix && cd emix
./emix cpm
```

or install the working tree, or the repository directly:

```sh
uv tool install .
uv tool install git+https://github.com/rdubar/emix
```

## Use

The current directory becomes the first drive. Mount more with `--mount`,
which is repeatable; drives are named in each personality's own style, so the
first mount is `A:` under CP/M, `DKA0:` under VMS and filemode `A` under CMS.

Settings can persist in `~/.config/emix/emix.toml` (`%APPDATA%\emix\emix.toml`
on Windows) — the personality to start, drives to mount, screen and hint
colours, whether to be strict. Command line always wins.

```sh
emix cpm                                  # . becomes A:
emix cpm --mount ~/Documents --mount ~/src  # A: and B:
emix vms --mount ~/Documents              # DKA0:
emix cms --mount ~/Documents              # filemode A
emix cpm -c "DIR *.TXT"                   # run one command and exit
```

### Real CP/M applications

With an emulator installed separately, Emix can open a host document in real
CP/M software. Set it up once (see [the manual](docs/MANUAL.md)), then:

```text
A>APPS
DDT        DDT.COM        DDT
ED         ED.COM         ED-CPM
MBASIC     MBASIC.COM     MBASIC
TE         TE.COM         TE-CPM

A>ED NEW.TXT

NEW FILE
     : *I
    1:  Dear Gary,
    2:  The BDOS is a triumph.
    3:
     : *E

DOCUMENT SESSION COMPLETE

  CREATED   NEW.TXT
  IGNORED   NEW.$$$  (the application's own backup)

Save these changes to the host? [Y/n]
```

That is Digital Research's `ED.COM` from 1982, executing real Z80
instructions, editing a file in your own folder. `MBASIC` gets you Microsoft
BASIC-85 5.29; `DDT` gets you the debugger.

Only the document you named is staged, so the program cannot see the rest of
the folder. The editor's own scratch file is named but not committed. The
write is atomic, and is refused if Emix sees that the host file changed while the guest ran (checked before the write, though a write landing inside the final handoff can still be lost).

## What is authentic and what is not

Emix aims to be recognisable, and says so when it is not.

**Authentic.** CP/M's six CCP built-ins are exactly the six it had; `PIP` and
`STAT` are listed separately because they were transient `.COM` programs
loaded from disk, not built-ins. `REN NEW=OLD` and `PIP DEST=SOURCE` keep
their surprising destination-first order. DCL verbs abbreviate to any
unambiguous prefix. `DELETE` demands an explicit version, as VMS did. CMS
answers `Ready; T=...` after every command and `Ready(00028);` after a
failure. Error messages follow each system's house format — `NO FILE`,
`%RMS-E-FNF, file not found`, `DMSxxx002E File 'X' not found`.

**Deliberately not authentic.** `ERA` confirms every erase, where CP/M only
confirmed for `ERA *.*`, because these are your real files. Names that do not
fit 8.3 are shown in full rather than truncated, because a listing that names
a file you cannot then type is worse than a misaligned column, so a long name
is shown as a reversible alias — `pyproject.toml` lists as `PYPROJ_1 TOM`, and
`TYPE PYPROJ_1.TOM` reads it back without ever renaming the host file. `ABOUT` and
`CREDIT` are shared Emix commands in every personality, as are `APPS`,
`EXPLAIN` and `STRICT`. `HELP`, `CLS`, `VER`,
`UNIX` and `DRIVES` are further Emix conveniences and are labelled as such in
`HELP`. File versions display as `;1` but only one copy is stored.

**Not yet built.** CP/M user areas, VMS directory syntax and real file
versions, CMS `EXEC` and `XEDIT`, and `SAVE`, which copied memory Emix does
not have. See
[docs/ROADMAP.md](docs/ROADMAP.md). More speculative jokes, atmosphere and optional AI
experiments live in [docs/IDEAS.md](docs/IDEAS.md).

## Assistance

Emix helps you find the period command without pretending to be a system that
accepted yours:

```text
$ ls
%DCL-W-IVVERB, unrecognized command verb - check validity and spelling
Emix: OpenVMS has no ls. To list the files, use DIRECTORY.

$ DELETE FOO.TXT
%DELETE-W-NOVER, explicit version number required
$ EXPLAIN
Emix: DELETE needs an explicit version, as in FILE.TXT;1. VMS kept every
Emix: version of a file, so a delete without one was too easy to get wrong.
```

Three rules make this safe to leave on: the authentic response prints first
and unaltered, every added line is marked `Emix:`, and **nothing is ever run
on a guess** — a hint names the command, you type it. That is the difference
between assistance that teaches the old system and assistance that replaces
it.

Output from commands the original system never had is printed in the hint
colour too, so nothing non-period is mistaken for period output. Each
personality decides: CP/M's `HELP` is painted because CP/M had none, while
VMS's stays plain because VMS had one.

Emix asks the terminal what colour it is — `COLORFGBG` first, then an OSC 11
query — and lights the whole session in **green phosphor on a dark screen**,
with hints in **amber** against it.
A light screen, or one that will not say, is left alone: green on white is
merely hard to read. The phosphor is set once and inherited, not wrapped
around every line, because output meant to read as the machine's own should
not be full of escape sequences.

Both ends of that are the **bright** ANSI colours, not the dim ones: many
colour schemes render ANSI green as a muddy yellow-green, which is neither
convincing as phosphor nor far enough from amber to read as a different
voice. Hints turn the phosphor back on behind them, so a hint interrupts the
screen rather than ending it.

`--screen cyan` (or `$EMIX_SCREEN`) picks another main colour, `--hint-colour
bright-white` (or `$EMIX_HINT_COLOUR`) another for the hints, and `none` turns
either off. `$NO_COLOR` and any non-terminal output disable both, because
escape codes in a pipe are corruption rather than decoration.

`STRICT ON`, or `--strict`, removes all of it. Scripts and pipes are strict by
default, because a script must not depend on a guess. Tab completion stays on
either way: it changes what you type, never what runs.

## Safety

Emix runs on your real home directory, so the boundaries are explicit and
tested:

- **Drives are sealed.** Every path is resolved through the host layer and
  checked against its drive root *after symlinks are followed*, so a symlink
  pointing out of a drive is neither readable nor listed. Directory
  traversal, absolute paths and separators in file names are rejected.
- **No shell is ever invoked.** Unknown CP/M commands are offered to the host
  as executables via `subprocess` with an argument list. Because there is no
  shell, `|`, `>`, `&&`, `$VAR` and backticks are literal arguments rather
  than operators. Exit Emix when you want a real shell. VMS and CMS do not
  fall through at all; use `RUN`/`SPAWN` and `CMS`.
- **Case ambiguity fails loudly.** On a case-sensitive host holding both
  `readme.txt` and `README.TXT`, Emix reports the ambiguity rather than
  silently picking whichever the filesystem happened to list first.
- **Destructive commands confirm**, and anything but an explicit `Y`/`YES`
  means no.

Erasing a file in Emix erases it on the host. That is the point of the
project, and the reason for everything above.

## Development

```sh
uv sync           # create the environment
uv run pytest     # the full suite
uv run ruff check . && uv run ruff format --check .
uv run mypy       # strict
```

Layout:

```
src/emix/
  errors.py         symbolic error codes, worded by each personality
  host.py           drives: containment, case folding, ambiguity
  shell.py          the REPL, verb table, abbreviation, host fallthrough
  cli.py            argument parsing, drive mounting, subcommands
  assist.py         hints, translations and explanations; never executes
  config.py         settings that persist between sessions
  personalities/    cpm.py, vms.py, cms.py — vocabulary and house style
  apps/             document sessions in real historical applications
```

Adding a personality means one module and one line in
`personalities/__init__.py`. Verbs are methods marked with `@verb`; the base
class handles parsing, dispatch, confirmation, history and errors.

## Status

Emix is an early experiment, and says so on PyPI: the classifier is Alpha.
Version 0.4 is useful for real file browsing today — on macOS, on Windows, and
on a Raspberry Pi 5, where the case-sensitive filesystem is the interesting
case and caught a bug that macOS structurally could not. Running real CP/M
applications over your own documents works, and needs an emulator you build
yourself.

It is one person's project. Bug reports are welcome, and reports of
**historical inaccuracy** are the most welcome of all — if Emix says something
the real machine never said, that is a bug, and there is an issue template for
it.

Release notes are in [CHANGELOG.md](CHANGELOG.md). The
[roadmap](docs/ROADMAP.md) covers where it goes next, including whether Emix
should eventually execute genuine CP/M `.COM` binaries in a sandbox — and why
that turns out to be less frightening than it sounds.

MIT licensed.
