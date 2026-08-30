# Emix

[![PyPI](https://img.shields.io/pypi/v/emix-shell)](https://pypi.org/project/emix-shell/)
[![CI](https://github.com/rdubar/emix/actions/workflows/ci.yml/badge.svg)](https://github.com/rdubar/emix/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/emix-shell)](https://pypi.org/project/emix-shell/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Emix lets a modern Unix machine pretend to be an older computer.

It is not a CPU emulator and it does not run historical binaries. It presents
the *commands, syntax, output formats and error messages* of historical
systems while operating on ordinary host files with ordinary host programs
underneath. Your files stay real files.

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

Emix has no runtime dependencies beyond Python 3.10 or newer. If `uv` warns
that `~/.local/bin` is not on your `PATH`, run `uv tool update-shell` and open
a new terminal.

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

```sh
emix cpm                                  # . becomes A:
emix cpm --mount ~/Documents --mount ~/src  # A: and B:
emix vms --mount ~/Documents              # DKA0:
emix cms --mount ~/Documents              # filemode A
emix cpm -c "DIR *.TXT"                   # run one command and exit
```

A CP/M session:

```text
EMIX 0.2.1
CP/M 2.2 PERSONALITY
A: /Users/rdubar/dev/emix
TYPE HELP FOR AVAILABLE COMMANDS.

A>DIR *.MD
A: README   MD  A: ROADMAP  MD

A>PIP NOTES.TXT=README.MD
A>STAT
A: R/W, SPACE: 96,508,384K
A>python3 hello.py
Hello from Unix
A>EXIT
RETURNING TO UNIX.
```

The same drive under DCL:

```text
$ DIRECTORY/SIZE

Directory DKA0:[000000]

README.MD;1                    15
ROADMAP.MD;1                   20

Total of 2 files, 35 blocks.

$ DELETE README.MD
%DELETE-W-NOVER, explicit version number required
```

and under CMS, where a file is three words and the system answers `Ready;`:

```text
LISTFILE
README   MD       A1
ROADMAP  MD       A1
Ready; T=0.01/0.01 21:42:19
```

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
a file you cannot then type is worse than a misaligned column. `HELP`, `CLS`,
`VER`, `UNIX` and `DRIVES` are Emix conveniences and are labelled as such in
`HELP`. File versions display as `;1` but only one copy is stored.

**Not yet built.** CP/M user areas, reversible 8.3 aliases, VMS directory
syntax and real file versions, CMS `EXEC` and `XEDIT`. See
[ROADMAP.md](ROADMAP.md).

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
uv run pytest     # 78 tests
uv run ruff check . && uv run ruff format --check .
uv run mypy       # strict
```

Layout:

```
src/emix/
  errors.py         symbolic error codes, worded by each personality
  host.py           drives: containment, case folding, ambiguity
  shell.py          the REPL, verb table, abbreviation, host fallthrough
  cli.py            argument parsing and drive mounting
  personalities/    cpm.py, vms.py, cms.py — vocabulary and house style
```

Adding a personality means one module and one line in
`personalities/__init__.py`. Verbs are methods marked with `@verb`; the base
class handles parsing, dispatch, confirmation, history and errors.

## Status

Emix is an early experiment. Version 0.2 is on PyPI and is useful for real
file browsing today, on macOS and on a Raspberry Pi 5 — the case-sensitive
filesystem there is the interesting case, and it caught a bug that macOS
structurally could not.

Release notes are in [CHANGELOG.md](CHANGELOG.md). The
[roadmap](ROADMAP.md) covers where it goes next, including whether Emix
should eventually execute genuine CP/M `.COM` binaries in a sandbox — and why
that turns out to be less frightening than it sounds.

MIT licensed.
